"""Unit tests for precinct crosswalk service."""

from unittest.mock import AsyncMock, MagicMock

from voter_api.services.precinct_crosswalk_service import (
    get_crosswalk_stats,
    upsert_crosswalk_entries,
)


class TestGetCrosswalkStats:
    """Tests for get_crosswalk_stats()."""

    async def test_returns_stats_dict(self) -> None:
        """Should return a dict with total_entries, counties_covered, avg_confidence."""
        mock_row = MagicMock()
        mock_row.total = 42
        mock_row.counties = 5
        mock_row.avg_confidence = 0.85123

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row

        session = AsyncMock()
        session.execute.return_value = mock_result

        stats = await get_crosswalk_stats(session)

        assert stats["total_entries"] == 42
        assert stats["counties_covered"] == 5
        assert stats["avg_confidence"] == 0.851

    async def test_handles_null_avg_confidence(self) -> None:
        """Should handle NULL avg_confidence (empty table) gracefully."""
        mock_row = MagicMock()
        mock_row.total = 0
        mock_row.counties = 0
        mock_row.avg_confidence = None

        mock_result = MagicMock()
        mock_result.one.return_value = mock_row

        session = AsyncMock()
        session.execute.return_value = mock_result

        stats = await get_crosswalk_stats(session)

        assert stats["total_entries"] == 0
        assert stats["counties_covered"] == 0
        assert stats["avg_confidence"] == 0.0


class TestUpsertCrosswalkEntries:
    """Tests for upsert_crosswalk_entries()."""

    async def test_empty_entries_returns_zero(self) -> None:
        """Empty entries list should return (0, 0) without DB interaction."""
        session = AsyncMock()
        inserted, updated = await upsert_crosswalk_entries(session, [])
        assert inserted == 0
        assert updated == 0
        session.execute.assert_not_called()

    async def test_upserts_entries_and_commits(self) -> None:
        """Should execute upsert for each entry and commit."""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        session.execute.return_value = mock_result

        entries = [
            {
                "county_code": "060",
                "county_name": "Fulton",
                "voter_precinct_code": "07A",
                "boundary_precinct_identifier": "FULTON-07A",
                "source": "spatial_join",
                "confidence": 0.95,
            },
            {
                "county_code": "044",
                "county_name": "DeKalb",
                "voter_precinct_code": "12B",
                "boundary_precinct_identifier": "DEKALB-12B",
                "source": "spatial_join",
                "confidence": 0.88,
            },
        ]

        inserted, updated = await upsert_crosswalk_entries(session, entries)

        assert inserted == 2
        assert session.execute.call_count == 2
        session.commit.assert_awaited_once()
