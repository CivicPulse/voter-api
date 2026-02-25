"""Unit tests for official location functions in geocoding_service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.geocoding_service import (
    clear_official_location_override,
    set_official_location_override,
    sync_official_location,
)


def _mock_voter(**overrides: object) -> MagicMock:
    """Create a mock Voter with official_* fields."""
    voter = MagicMock()
    voter.id = uuid.uuid4()
    voter.official_latitude = None
    voter.official_longitude = None
    voter.official_point = None
    voter.official_source = None
    voter.official_is_override = False
    for key, value in overrides.items():
        setattr(voter, key, value)
    return voter


def _mock_location(*, latitude: float = 33.749, longitude: float = -84.388, source_type: str = "census") -> MagicMock:
    """Create a mock GeocodedLocation."""
    loc = MagicMock()
    loc.latitude = latitude
    loc.longitude = longitude
    loc.source_type = source_type
    loc.point = MagicMock()
    loc.confidence_score = 0.95
    return loc


class TestSyncOfficialLocation:
    """Tests for sync_official_location."""

    @pytest.mark.asyncio
    async def test_updates_from_best_geocode(self) -> None:
        session = AsyncMock()
        voter = _mock_voter()
        best_loc = _mock_location()

        result = MagicMock()
        result.scalar_one_or_none.return_value = best_loc
        session.execute.return_value = result

        await sync_official_location(session, voter)

        assert voter.official_latitude == pytest.approx(33.749)
        assert voter.official_longitude == pytest.approx(-84.388)
        assert voter.official_source == "census"
        assert voter.official_point is best_loc.point
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_override_is_true(self) -> None:
        session = AsyncMock()
        voter = _mock_voter(
            official_is_override=True,
            official_latitude=34.0,
            official_longitude=-85.0,
            official_source="admin",
        )

        await sync_official_location(session, voter)

        # Should not have changed
        assert voter.official_latitude == pytest.approx(34.0)
        assert voter.official_source == "admin"
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_when_no_geocodes(self) -> None:
        session = AsyncMock()
        voter = _mock_voter(
            official_latitude=33.749,
            official_longitude=-84.388,
            official_source="census",
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        await sync_official_location(session, voter)

        assert voter.official_latitude is None
        assert voter.official_longitude is None
        assert voter.official_point is None
        assert voter.official_source is None


class TestSetOfficialLocationOverride:
    """Tests for set_official_location_override."""

    @pytest.mark.asyncio
    async def test_sets_coords_and_override(self) -> None:
        session = AsyncMock()
        voter = _mock_voter()

        result = MagicMock()
        result.scalar_one_or_none.return_value = voter
        session.execute.return_value = result

        returned = await set_official_location_override(session, voter.id, 34.0, -85.0)

        assert returned is voter
        assert voter.official_latitude == pytest.approx(34.0)
        assert voter.official_longitude == pytest.approx(-85.0)
        assert voter.official_source == "admin"
        assert voter.official_is_override is True
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_for_missing_voter(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        with pytest.raises(ValueError, match="not found"):
            await set_official_location_override(session, uuid.uuid4(), 34.0, -85.0)


class TestClearOfficialLocationOverride:
    """Tests for clear_official_location_override."""

    @pytest.mark.asyncio
    async def test_reverts_to_best_geocode(self) -> None:
        session = AsyncMock()
        voter = _mock_voter(
            official_is_override=True,
            official_latitude=34.0,
            official_longitude=-85.0,
            official_source="admin",
        )

        best_loc = _mock_location(latitude=33.749, longitude=-84.388, source_type="census")

        # First execute: find voter; Second execute: sync (find best geocode)
        voter_result = MagicMock()
        voter_result.scalar_one_or_none.return_value = voter
        geocode_result = MagicMock()
        geocode_result.scalar_one_or_none.return_value = best_loc
        session.execute.side_effect = [voter_result, geocode_result]

        returned = await clear_official_location_override(session, voter.id)

        assert returned is voter
        assert voter.official_is_override is False
        # sync_official_location was called since override was cleared
        assert voter.official_latitude == pytest.approx(33.749)
        assert voter.official_source == "census"

    @pytest.mark.asyncio
    async def test_raises_for_missing_voter(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        with pytest.raises(ValueError, match="not found"):
            await clear_official_location_override(session, uuid.uuid4())
