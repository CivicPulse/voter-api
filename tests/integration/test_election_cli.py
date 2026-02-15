"""Integration tests for the election CLI commands."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from voter_api.cli.app import app
from voter_api.schemas.election import RefreshResponse

runner = CliRunner()


@pytest.fixture
def mock_engine():
    """Mock _refresh_impl to isolate CLI argument handling."""
    with patch("voter_api.cli.election_cmd._refresh_impl") as mock_impl:
        yield mock_impl


class TestElectionRefreshCLI:
    """Tests for the `election refresh` CLI command."""

    def test_refresh_single_election(self, mock_engine):
        """Refreshing a single election by ID invokes _refresh_impl with the ID."""
        eid = uuid.uuid4()

        async def _fake_impl(election_id_str):
            assert election_id_str == str(eid)

        mock_engine.side_effect = _fake_impl

        result = runner.invoke(app, ["election", "refresh", "--election-id", str(eid)])
        assert result.exit_code == 0
        mock_engine.assert_called_once()

    def test_refresh_all_active(self, mock_engine):
        """Refreshing without --election-id passes None to _refresh_impl."""

        async def _fake_impl(election_id_str):
            assert election_id_str is None

        mock_engine.side_effect = _fake_impl

        result = runner.invoke(app, ["election", "refresh"])
        assert result.exit_code == 0
        mock_engine.assert_called_once()

    def test_refresh_invalid_uuid(self):
        """Passing an invalid UUID triggers an error."""
        result = runner.invoke(app, ["election", "refresh", "--election-id", "not-a-uuid"])
        assert result.exit_code != 0


class TestElectionRefreshImplIntegration:
    """Tests for _refresh_impl with mocked service layer."""

    def test_single_election_output(self):
        """Refresh of a single election outputs counties and precincts."""
        eid = uuid.uuid4()
        mock_result = RefreshResponse(
            election_id=eid,
            refreshed_at=datetime.now(UTC),
            precincts_reporting=100,
            precincts_participating=120,
            counties_updated=5,
        )

        with (
            patch("voter_api.core.config.get_settings") as mock_settings,
            patch("voter_api.core.logging.setup_logging"),
            patch("voter_api.core.database.init_engine"),
            patch("voter_api.core.database.dispose_engine", new_callable=AsyncMock),
            patch("voter_api.core.database.get_session_factory") as mock_factory,
            patch(
                "voter_api.services.election_service.refresh_single_election", new_callable=AsyncMock
            ) as mock_refresh,
        ):
            mock_settings.return_value.database_url = "sqlite+aiosqlite:///:memory:"
            mock_settings.return_value.log_level = "WARNING"
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_refresh.return_value = mock_result

            result = runner.invoke(app, ["election", "refresh", "--election-id", str(eid)])

            assert result.exit_code == 0
            assert "5 counties updated" in result.output
            assert "100/120 precincts reporting" in result.output

    def test_refresh_all_output(self):
        """Refresh all prints count of refreshed elections."""
        with (
            patch("voter_api.core.config.get_settings") as mock_settings,
            patch("voter_api.core.logging.setup_logging"),
            patch("voter_api.core.database.init_engine"),
            patch("voter_api.core.database.dispose_engine", new_callable=AsyncMock),
            patch("voter_api.core.database.get_session_factory") as mock_factory,
            patch(
                "voter_api.services.election_service.refresh_all_active_elections", new_callable=AsyncMock
            ) as mock_refresh_all,
        ):
            mock_settings.return_value.database_url = "sqlite+aiosqlite:///:memory:"
            mock_settings.return_value.log_level = "WARNING"
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_refresh_all.return_value = 3

            result = runner.invoke(app, ["election", "refresh"])

            assert result.exit_code == 0
            assert "Refreshed 3 active election(s)" in result.output

    def test_refresh_handles_value_error(self):
        """Refresh single election with non-existent ID propagates the error."""
        eid = uuid.uuid4()

        with (
            patch("voter_api.core.config.get_settings") as mock_settings,
            patch("voter_api.core.logging.setup_logging"),
            patch("voter_api.core.database.init_engine"),
            patch("voter_api.core.database.dispose_engine", new_callable=AsyncMock),
            patch("voter_api.core.database.get_session_factory") as mock_factory,
            patch(
                "voter_api.services.election_service.refresh_single_election", new_callable=AsyncMock
            ) as mock_refresh,
        ):
            mock_settings.return_value.database_url = "sqlite+aiosqlite:///:memory:"
            mock_settings.return_value.log_level = "WARNING"
            mock_session = AsyncMock()
            mock_factory.return_value.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_refresh.side_effect = ValueError("Election not found")

            result = runner.invoke(app, ["election", "refresh", "--election-id", str(eid)])
            assert result.exit_code != 0
