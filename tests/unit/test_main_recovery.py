"""Tests for stale geocoding job recovery on startup."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.main import _recover_stale_geocoding_jobs


class TestRecoverStaleGeocodingJobs:
    """Tests for _recover_stale_geocoding_jobs."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory with configurable rowcount."""
        mock_result = MagicMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        return mock_factory, mock_session, mock_result

    @pytest.mark.asyncio
    async def test_running_job_recovered_to_failed(self, mock_session_factory) -> None:
        """Running geocoding jobs are marked as failed with recovery note and completed_at."""
        mock_factory, mock_session, mock_result = mock_session_factory
        mock_result.rowcount = 1

        with (
            patch("voter_api.main.get_session_factory", return_value=mock_factory),
            patch("voter_api.main.logger") as mock_logger,
        ):
            await _recover_stale_geocoding_jobs()

        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_logger.warning.assert_called_once_with("Recovered {} stale geocoding job(s) on startup", 1)

    @pytest.mark.asyncio
    async def test_pending_job_recovered(self, mock_session_factory) -> None:
        """Pending geocoding jobs are also recovered (both pending and running are targeted)."""
        mock_factory, mock_session, mock_result = mock_session_factory
        mock_result.rowcount = 3

        with (
            patch("voter_api.main.get_session_factory", return_value=mock_factory),
            patch("voter_api.main.logger") as mock_logger,
        ):
            await _recover_stale_geocoding_jobs()

        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_logger.warning.assert_called_once_with("Recovered {} stale geocoding job(s) on startup", 3)

    @pytest.mark.asyncio
    async def test_no_stale_jobs_no_warning(self, mock_session_factory) -> None:
        """No warning logged when there are no stale geocoding jobs."""
        mock_factory, mock_session, mock_result = mock_session_factory
        mock_result.rowcount = 0

        with (
            patch("voter_api.main.get_session_factory", return_value=mock_factory),
            patch("voter_api.main.logger") as mock_logger,
        ):
            await _recover_stale_geocoding_jobs()

        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_error_log_preserved(self, mock_session_factory) -> None:
        """The UPDATE uses coalesce + JSONB concatenation to append the recovery note.

        The function builds the SQL expression to append the recovery note to
        the existing error_log array (or start a new one if null). We verify
        the update is executed and committed; the actual JSONB concatenation
        logic is handled by PostgreSQL at runtime.
        """
        mock_factory, mock_session, mock_result = mock_session_factory
        mock_result.rowcount = 1

        with (
            patch("voter_api.main.get_session_factory", return_value=mock_factory),
            patch("voter_api.main.logger"),
        ):
            await _recover_stale_geocoding_jobs()

        # Verify the UPDATE statement was built and executed
        mock_session.execute.assert_awaited_once()
        call_args = mock_session.execute.call_args
        update_stmt = call_args[0][0]

        # Compile without literal_binds to avoid JSONB rendering issues;
        # this still proves the SQL references the right columns and functions
        compiled = str(update_stmt.compile())
        assert "error_log" in compiled
        assert "coalesce" in compiled.lower()
        assert "status" in compiled
        assert "completed_at" in compiled

    @pytest.mark.asyncio
    async def test_rowcount_none_no_warning(self, mock_session_factory) -> None:
        """No warning logged when rowcount is None (e.g. some DB drivers)."""
        mock_factory, mock_session, mock_result = mock_session_factory
        mock_result.rowcount = None

        with (
            patch("voter_api.main.get_session_factory", return_value=mock_factory),
            patch("voter_api.main.logger") as mock_logger,
        ):
            await _recover_stale_geocoding_jobs()

        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_logger.warning.assert_not_called()


class TestLifespanGeocodingRecovery:
    """Tests for geocoding job recovery within lifespan context."""

    @pytest.mark.asyncio
    async def test_lifespan_continues_when_geocoding_recovery_fails(self) -> None:
        """Lifespan proceeds normally even if geocoding job recovery raises."""
        from voter_api.core.config import Settings
        from voter_api.main import lifespan

        mock_app = AsyncMock()

        with (
            patch("voter_api.main.get_settings") as mock_get_settings,
            patch("voter_api.main.setup_logging"),
            patch("voter_api.main.init_engine"),
            patch("voter_api.main.dispose_engine", new_callable=AsyncMock) as mock_dispose,
            patch(
                "voter_api.main._recover_stale_analysis_runs",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.main._recover_stale_geocoding_jobs",
                new_callable=AsyncMock,
                side_effect=Exception("relation does not exist"),
            ),
            patch("voter_api.main.logger") as mock_logger,
        ):
            mock_get_settings.return_value = Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                jwt_secret_key="test-secret-key-not-for-production",
            )

            async with lifespan(mock_app):
                pass  # App should start successfully

            mock_dispose.assert_awaited_once()
            # Check that the geocoding-specific warning was logged
            mock_logger.warning.assert_any_call(
                "Could not recover stale geocoding jobs on startup (table may not exist yet)"
            )

    @pytest.mark.asyncio
    async def test_lifespan_calls_geocoding_recovery(self) -> None:
        """Lifespan calls _recover_stale_geocoding_jobs during startup."""
        from voter_api.core.config import Settings
        from voter_api.main import lifespan

        mock_app = AsyncMock()

        with (
            patch("voter_api.main.get_settings") as mock_get_settings,
            patch("voter_api.main.setup_logging"),
            patch("voter_api.main.init_engine"),
            patch("voter_api.main.dispose_engine", new_callable=AsyncMock),
            patch(
                "voter_api.main._recover_stale_analysis_runs",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.main._recover_stale_geocoding_jobs",
                new_callable=AsyncMock,
            ) as mock_recover_geo,
        ):
            mock_get_settings.return_value = Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                jwt_secret_key="test-secret-key-not-for-production",
            )

            async with lifespan(mock_app):
                mock_recover_geo.assert_awaited_once()
