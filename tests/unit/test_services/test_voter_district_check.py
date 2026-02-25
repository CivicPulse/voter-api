"""Unit tests for check_voter_districts service function."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from voter_api.services.voter_service import check_voter_districts


def _make_voter(**overrides: object) -> MagicMock:
    """Create a mock voter with all standard fields."""
    voter = MagicMock()
    voter.id = uuid4()
    voter.county = "BIBB"
    voter.voter_registration_number = "12345678"
    voter.status = "ACTIVE"
    voter.last_name = "SMITH"
    voter.first_name = "JOHN"

    # Districts
    voter.county_precinct = "BB01"
    voter.county_precinct_description = "Bibb 01"
    voter.municipal_precinct = None
    voter.municipal_precinct_description = None
    voter.congressional_district = "8"
    voter.state_senate_district = "18"
    voter.state_house_district = "142"
    voter.judicial_district = None
    voter.county_commission_district = "1"
    voter.school_board_district = None
    voter.city_council_district = None
    voter.municipal_school_board_district = None
    voter.water_board_district = None
    voter.super_council_district = None
    voter.super_commissioner_district = None
    voter.super_school_board_district = None
    voter.fire_district = None
    voter.combo = None
    voter.land_lot = None
    voter.land_district = None
    voter.municipality = "MACON"

    # Dates
    voter.registration_date = date(2020, 1, 15)
    voter.last_modified_date = date(2024, 6, 1)
    voter.date_of_last_contact = None
    voter.last_vote_date = date(2024, 11, 5)
    voter.voter_created_date = None
    voter.last_party_voted = "D"

    # Tracking
    voter.present_in_latest_import = True
    voter.soft_deleted_at = None
    voter.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    voter.updated_at = datetime(2024, 6, 1, tzinfo=UTC)

    # Relationships
    voter.geocoded_locations = []

    for key, value in overrides.items():
        setattr(voter, key, value)

    return voter


def _make_location(*, is_primary: bool = True) -> MagicMock:
    """Create a mock geocoded location."""
    loc = MagicMock()
    loc.is_primary = is_primary
    loc.latitude = 32.8407
    loc.longitude = -83.6324
    loc.source_type = "census"
    loc.confidence_score = 100.0
    return loc


@pytest.mark.asyncio
class TestCheckVoterDistricts:
    """Tests for check_voter_districts."""

    async def test_voter_not_found_returns_none(self) -> None:
        session = AsyncMock()
        with patch(
            "voter_api.services.voter_service.get_voter_detail",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await check_voter_districts(session, uuid4())
        assert result is None

    async def test_no_geocoded_location_returns_not_geocoded(self) -> None:
        voter = _make_voter()
        session = AsyncMock()
        with patch(
            "voter_api.services.voter_service.get_voter_detail",
            new_callable=AsyncMock,
            return_value=voter,
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None
        assert result["match_status"] == "not-geocoded"
        assert result["geocoded_point"] is None
        assert result["comparisons"] == []
        assert result["mismatch_count"] == 0

    async def test_all_districts_match(self) -> None:
        loc = _make_location()
        voter = _make_voter(geocoded_locations=[loc])
        session = AsyncMock()

        determined = {
            "congressional": "8",
            "state_senate": "18",
            "state_house": "142",
            "county_commission": "1",
            "county_precinct": "BB01",
        }

        with (
            patch(
                "voter_api.services.voter_service.get_voter_detail",
                new_callable=AsyncMock,
                return_value=voter,
            ),
            patch(
                "voter_api.services.voter_service.find_voter_boundaries",
                new_callable=AsyncMock,
                return_value=determined,
            ),
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None
        assert result["match_status"] == "match"
        assert result["mismatch_count"] == 0
        assert result["geocoded_point"]["latitude"] == 32.8407

        # All comparisons should be "match"
        for comp in result["comparisons"]:
            if comp["status"] in ("match", "registered-only", "determined-only"):
                continue
            pytest.fail(f"Unexpected mismatch: {comp}")

    async def test_district_mismatch(self) -> None:
        loc = _make_location()
        voter = _make_voter(geocoded_locations=[loc])
        session = AsyncMock()

        # county_commission differs: registered "1" vs determined "5"
        determined = {
            "congressional": "8",
            "state_senate": "18",
            "state_house": "142",
            "county_commission": "5",
            "county_precinct": "BB01",
        }

        with (
            patch(
                "voter_api.services.voter_service.get_voter_detail",
                new_callable=AsyncMock,
                return_value=voter,
            ),
            patch(
                "voter_api.services.voter_service.find_voter_boundaries",
                new_callable=AsyncMock,
                return_value=determined,
            ),
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None
        assert result["match_status"] == "mismatch-district"
        assert result["mismatch_count"] == 1

        mismatches = [c for c in result["comparisons"] if c["status"] == "mismatch"]
        assert len(mismatches) == 1
        assert mismatches[0]["boundary_type"] == "county_commission"
        assert mismatches[0]["registered_value"] == "1"
        assert mismatches[0]["determined_value"] == "5"

    async def test_no_boundaries_found_returns_unable_to_analyze(self) -> None:
        loc = _make_location()
        voter = _make_voter(geocoded_locations=[loc])
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_service.get_voter_detail",
                new_callable=AsyncMock,
                return_value=voter,
            ),
            patch(
                "voter_api.services.voter_service.find_voter_boundaries",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None
        assert result["match_status"] == "unable-to-analyze"

    async def test_comparisons_include_registered_only_and_determined_only(self) -> None:
        loc = _make_location()
        # Voter has congressional and state_senate registered but not school_board
        voter = _make_voter(
            geocoded_locations=[loc],
            congressional_district="8",
            state_senate_district="18",
            state_house_district=None,
            county_commission_district=None,
            county_precinct=None,
        )
        session = AsyncMock()

        # Determined has congressional, school_board, but not state_senate
        determined = {
            "congressional": "8",
            "school_board": "3",
        }

        with (
            patch(
                "voter_api.services.voter_service.get_voter_detail",
                new_callable=AsyncMock,
                return_value=voter,
            ),
            patch(
                "voter_api.services.voter_service.find_voter_boundaries",
                new_callable=AsyncMock,
                return_value=determined,
            ),
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None

        statuses = {c["boundary_type"]: c["status"] for c in result["comparisons"]}
        assert statuses["congressional"] == "match"
        assert statuses["state_senate"] == "registered-only"
        assert statuses["school_board"] == "determined-only"

    async def test_precinct_mismatch(self) -> None:
        loc = _make_location()
        voter = _make_voter(
            geocoded_locations=[loc],
            congressional_district="8",
            county_precinct="BB01",
        )
        session = AsyncMock()

        determined = {
            "congressional": "8",
            "county_precinct": "BB02",
        }

        with (
            patch(
                "voter_api.services.voter_service.get_voter_detail",
                new_callable=AsyncMock,
                return_value=voter,
            ),
            patch(
                "voter_api.services.voter_service.find_voter_boundaries",
                new_callable=AsyncMock,
                return_value=determined,
            ),
        ):
            result = await check_voter_districts(session, voter.id)

        assert result is not None
        assert result["match_status"] == "mismatch-precinct"
        assert result["mismatch_count"] == 1
