"""Tests for spatial analysis module."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.lib.analyzer.spatial import find_voter_boundaries, find_voter_boundaries_batch


def _mock_geocoded_location(voter_id: uuid.UUID | None = None) -> MagicMock:
    """Create a mock GeocodedLocation."""
    loc = MagicMock()
    loc.voter_id = voter_id or uuid.uuid4()
    loc.point = MagicMock()
    loc.latitude = 33.749
    loc.longitude = -84.388
    return loc


class TestFindVoterBoundaries:
    """Tests for find_voter_boundaries."""

    @pytest.mark.asyncio
    async def test_returns_boundaries_for_point(self) -> None:
        session = AsyncMock()
        loc = _mock_geocoded_location()

        # Mock: one boundary contains the point
        result = MagicMock()
        result.all.return_value = [
            ("congressional", "05"),
            ("state_senate", "34"),
        ]
        session.execute.return_value = result

        boundaries = await find_voter_boundaries(session, loc)
        assert boundaries == {"congressional": "05", "state_senate": "34"}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_boundaries(self) -> None:
        session = AsyncMock()
        loc = _mock_geocoded_location()

        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result

        boundaries = await find_voter_boundaries(session, loc)
        assert boundaries == {}

    @pytest.mark.asyncio
    async def test_tiebreaking_by_alphabetical_identifier(self) -> None:
        """When point falls in multiple boundaries of same type, pick lowest alphabetically."""
        session = AsyncMock()
        loc = _mock_geocoded_location()

        result = MagicMock()
        result.all.return_value = [
            ("congressional", "06"),
            ("congressional", "05"),
        ]
        session.execute.return_value = result

        boundaries = await find_voter_boundaries(session, loc)
        assert boundaries["congressional"] == "05"  # Sorted, lowest first


class TestFindVoterBoundariesBatch:
    """Tests for find_voter_boundaries_batch."""

    @pytest.mark.asyncio
    async def test_processes_multiple_locations(self) -> None:
        session = AsyncMock()
        loc1 = _mock_geocoded_location()
        loc2 = _mock_geocoded_location()

        # Each call to find_voter_boundaries returns different boundaries
        result1 = MagicMock()
        result1.all.return_value = [("congressional", "05")]
        result2 = MagicMock()
        result2.all.return_value = [("congressional", "06")]
        session.execute.side_effect = [result1, result2]

        results = await find_voter_boundaries_batch(session, [loc1, loc2])
        assert len(results) == 2
        assert results[str(loc1.voter_id)] == {"congressional": "05"}
        assert results[str(loc2.voter_id)] == {"congressional": "06"}

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self) -> None:
        session = AsyncMock()

        results = await find_voter_boundaries_batch(session, [])
        assert results == {}
