"""Tests for voter_stats_service — aggregate voter registration counts for boundaries."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.voter_stats_service import get_voter_stats_for_boundary


def _make_session(rows: list[tuple[str, int]]) -> AsyncMock:
    """Create an AsyncMock session whose execute() returns a sync result with .all()."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    session.execute.return_value = mock_result
    return session


class TestGetVoterStatsForBoundary:
    """Tests for get_voter_stats_for_boundary."""

    @pytest.mark.asyncio
    async def test_returns_none_for_unmapped_boundary_type(self) -> None:
        """Boundary types not in BOUNDARY_TYPE_TO_VOTER_FIELD return None."""
        session = AsyncMock()
        result = await get_voter_stats_for_boundary(session, "psc", "1")
        assert result is None
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_for_us_senate(self) -> None:
        """us_senate boundary type is not mapped and returns None."""
        session = AsyncMock()
        result = await get_voter_stats_for_boundary(session, "us_senate", "1")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_stats_for_congressional_district(self) -> None:
        """Congressional district returns total and by_status from grouped query."""
        session = _make_session([("A", 5000), ("I", 300)])

        result = await get_voter_stats_for_boundary(session, "congressional", "5")

        assert result is not None
        assert result.total == 5300
        assert len(result.by_status) == 2
        assert result.by_status[0].status == "A"
        assert result.by_status[0].count == 5000
        assert result.by_status[1].status == "I"
        assert result.by_status[1].count == 300
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_stats_for_county_commission_with_county_filter(self) -> None:
        """County-scoped boundary types include county filter in query."""
        session = _make_session([("A", 1200)])

        result = await get_voter_stats_for_boundary(session, "county_commission", "3", county="Bibb")

        assert result is not None
        assert result.total == 1200
        assert len(result.by_status) == 1
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_total_when_no_voters(self) -> None:
        """Returns total=0 and empty by_status when no voters match."""
        session = _make_session([])

        result = await get_voter_stats_for_boundary(session, "state_house", "180")

        assert result is not None
        assert result.total == 0
        assert result.by_status == []

    @pytest.mark.asyncio
    async def test_county_boundary_uses_county_name_override(self) -> None:
        """County boundary type uses county_name_override for voter lookup."""
        session = _make_session([("A", 10000)])

        result = await get_voter_stats_for_boundary(session, "county", "13121", county_name_override="Fulton")

        assert result is not None
        assert result.total == 10000
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_county_boundary_without_override_returns_none(self) -> None:
        """County boundary type without county_name_override returns None."""
        session = AsyncMock()

        with patch("voter_api.services.voter_stats_service.logger"):
            result = await get_voter_stats_for_boundary(session, "county", "13121")

        assert result is None
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_stats_for_fire_district(self) -> None:
        """fire_district boundary type is correctly mapped after the key fix."""
        session = _make_session([("A", 800)])

        result = await get_voter_stats_for_boundary(session, "fire_district", "2", county="Clarke")

        assert result is not None
        assert result.total == 800

    @pytest.mark.asyncio
    async def test_numeric_identifier_executes_query(self) -> None:
        """Numeric boundary identifiers (e.g. bare "5" from shapefile int field) execute a query."""
        session = _make_session([("A", 3000)])

        result = await get_voter_stats_for_boundary(session, "congressional", "5")

        assert result is not None
        assert result.total == 3000
        # Query must run — normalization should not short-circuit execution
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_zero_padded_identifier_executes_query(self) -> None:
        """Zero-padded boundary identifiers (e.g. "005" from voter CSV) also execute a query."""
        session = _make_session([("A", 3000)])

        result = await get_voter_stats_for_boundary(session, "state_senate", "005")

        assert result is not None
        assert result.total == 3000
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_alphanumeric_identifier_uses_exact_match(self) -> None:
        """Non-numeric identifiers (e.g. precinct codes like '001A') use exact string comparison."""
        session = _make_session([("A", 500)])

        result = await get_voter_stats_for_boundary(session, "county_precinct", "001A", county="Bibb")

        assert result is not None
        assert result.total == 500
        session.execute.assert_awaited_once()
