"""Unit tests for cooperative cancellation in process_geocoding_job().

Tests the cooperative cancellation check at the top of the batch processing
loop that re-reads job status from the database and stops early if the job
has been externally set to a terminal status (cancelled, failed, completed).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from voter_api.models.geocoding_job import GeocodingJob
from voter_api.services.geocoding_service import (
    TERMINAL_STATUSES,
    process_geocoding_job,
)


def _make_job(**overrides: object) -> GeocodingJob:
    """Create a GeocodingJob with sensible defaults for testing."""
    job = GeocodingJob(
        id=overrides.pop("id", uuid.uuid4()),
        provider=overrides.pop("provider", "census"),
        status=overrides.pop("status", "pending"),
        force_regeocode=overrides.pop("force_regeocode", False),
        county=overrides.pop("county", None),
    )
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


def _make_mock_geocoder() -> MagicMock:
    """Create a mock geocoder provider."""
    geocoder = MagicMock()
    geocoder.provider_name = "census"
    geocoder.rate_limit_delay = 0
    geocoder.geocode = AsyncMock(return_value=None)
    return geocoder


class TestCooperativeCancellation:
    """Tests for cooperative cancellation in process_geocoding_job()."""

    async def test_cancelled_mid_batch_stops_and_preserves_progress(self) -> None:
        """Job status changed to 'cancelled' mid-batch stops processing and returns early."""
        job = _make_job(
            status="pending",
            last_processed_voter_offset=None,
            processed=None,
            succeeded=None,
            failed=None,
            cache_hits=None,
        )
        mock_session = AsyncMock()

        mock_geocoder = _make_mock_geocoder()

        # Track the sequence of session.execute() calls:
        # 1. Initial commit (status = "running")
        # 2. Count query -> returns total of 10
        # 3. Commit after setting total_records
        # 4. Status re-read query -> returns "cancelled"
        # 5. Commit after saving progress

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        status_result = MagicMock()
        status_result.scalar_one.return_value = "cancelled"

        mock_session.execute = AsyncMock(side_effect=[count_result, status_result])

        with (
            patch(
                "voter_api.services.geocoding_service.get_configured_providers",
                return_value=[mock_geocoder],
            ),
            patch(
                "voter_api.services.geocoding_service.get_settings",
                return_value=MagicMock(),
            ),
        ):
            result = await process_geocoding_job(mock_session, job, batch_size=5)

        # Job should have the externally-set status preserved
        assert result.status == "cancelled"
        # Progress counters should be saved (all zero since no voters processed yet)
        assert result.processed == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.cache_hits == 0
        # Should NOT have reached "completed" status
        assert result.completed_at is None

    async def test_failed_mid_batch_stops_and_preserves_progress(self) -> None:
        """Job status changed to 'failed' mid-batch stops processing and returns early."""
        job = _make_job(
            status="pending",
            last_processed_voter_offset=None,
            processed=None,
            succeeded=None,
            failed=None,
            cache_hits=None,
        )
        mock_session = AsyncMock()

        mock_geocoder = _make_mock_geocoder()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 10

        status_result = MagicMock()
        status_result.scalar_one.return_value = "failed"

        mock_session.execute = AsyncMock(side_effect=[count_result, status_result])

        with (
            patch(
                "voter_api.services.geocoding_service.get_configured_providers",
                return_value=[mock_geocoder],
            ),
            patch(
                "voter_api.services.geocoding_service.get_settings",
                return_value=MagicMock(),
            ),
        ):
            result = await process_geocoding_job(mock_session, job, batch_size=5)

        # Job should have the externally-set status preserved
        assert result.status == "failed"
        # Progress counters should be saved
        assert result.processed == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.cache_hits == 0
        assert result.completed_at is None

    async def test_running_status_continues_processing(self) -> None:
        """Job status remains 'running' allows processing to continue past the check."""
        job = _make_job(
            status="pending",
            last_processed_voter_offset=None,
            processed=None,
            succeeded=None,
            failed=None,
            cache_hits=None,
        )
        mock_session = AsyncMock()

        mock_geocoder = _make_mock_geocoder()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 5

        status_result = MagicMock()
        status_result.scalar_one.return_value = "running"

        # After status check returns "running", the batch query returns empty list
        # (no voters to process), which breaks the while loop naturally.
        batch_result = MagicMock()
        batch_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, status_result, batch_result])

        with (
            patch(
                "voter_api.services.geocoding_service.get_configured_providers",
                return_value=[mock_geocoder],
            ),
            patch(
                "voter_api.services.geocoding_service.get_settings",
                return_value=MagicMock(),
            ),
        ):
            result = await process_geocoding_job(mock_session, job, batch_size=5)

        # Job should reach "completed" since status check passed and loop ended naturally
        assert result.status == "completed"
        assert result.completed_at is not None
        # The batch query was executed (meaning we got past the cancellation check)
        assert mock_session.execute.await_count == 3


class TestTerminalStatuses:
    """Tests for the TERMINAL_STATUSES constant."""

    def test_terminal_statuses_contains_expected_values(self) -> None:
        """TERMINAL_STATUSES includes completed, failed, and cancelled."""
        assert "completed" in TERMINAL_STATUSES
        assert "failed" in TERMINAL_STATUSES
        assert "cancelled" in TERMINAL_STATUSES

    def test_terminal_statuses_excludes_active_values(self) -> None:
        """TERMINAL_STATUSES does not include running or pending."""
        assert "running" not in TERMINAL_STATUSES
        assert "pending" not in TERMINAL_STATUSES

    def test_terminal_statuses_is_frozenset(self) -> None:
        """TERMINAL_STATUSES is immutable."""
        assert isinstance(TERMINAL_STATUSES, frozenset)
