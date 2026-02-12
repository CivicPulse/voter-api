"""Tests for the voter service module."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from voter_api.services.voter_service import build_voter_detail_dict


def _make_voter(**overrides: object) -> MagicMock:
    """Create a mock voter with all standard fields."""
    voter = MagicMock()
    voter.id = uuid4()
    voter.county = "FULTON"
    voter.voter_registration_number = "12345678"
    voter.status = "ACTIVE"
    voter.status_reason = None
    voter.last_name = "SMITH"
    voter.first_name = "JOHN"
    voter.middle_name = "A"
    voter.suffix = None
    voter.birth_year = 1990
    voter.race = "WH"
    voter.gender = "M"

    # Address fields
    voter.residence_street_number = "123"
    voter.residence_pre_direction = None
    voter.residence_street_name = "MAIN"
    voter.residence_street_type = "ST"
    voter.residence_post_direction = None
    voter.residence_apt_unit_number = None
    voter.residence_city = "ATLANTA"
    voter.residence_zipcode = "30301"

    voter.mailing_street_number = None
    voter.mailing_street_name = None
    voter.mailing_apt_unit_number = None
    voter.mailing_city = None
    voter.mailing_zipcode = None
    voter.mailing_state = None
    voter.mailing_country = None

    # Districts
    voter.county_precinct = "SS01"
    voter.county_precinct_description = "Sandy Springs 01"
    voter.municipal_precinct = None
    voter.municipal_precinct_description = None
    voter.congressional_district = "05"
    voter.state_senate_district = "34"
    voter.state_house_district = "55"
    voter.judicial_district = None
    voter.county_commission_district = None
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
    voter.municipality = "ATLANTA"

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


def _make_location(*, is_primary: bool = False) -> MagicMock:
    """Create a mock geocoded location."""
    loc = MagicMock()
    loc.is_primary = is_primary
    loc.latitude = 33.749
    loc.longitude = -84.388
    loc.source_type = "census"
    loc.confidence_score = 0.95
    return loc


class TestBuildVoterDetailDict:
    """Tests for build_voter_detail_dict."""

    def test_basic_fields(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        assert result["county"] == "FULTON"
        assert result["voter_registration_number"] == "12345678"
        assert result["status"] == "ACTIVE"
        assert result["last_name"] == "SMITH"
        assert result["first_name"] == "JOHN"

    def test_nested_residence_address(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        addr = result["residence_address"]
        assert addr["street_number"] == "123"
        assert addr["street_name"] == "MAIN"
        assert addr["street_type"] == "ST"
        assert addr["city"] == "ATLANTA"
        assert addr["zipcode"] == "30301"

    def test_nested_mailing_address(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        addr = result["mailing_address"]
        assert addr["street_number"] is None
        assert addr["street_name"] is None

    def test_nested_registered_districts(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        districts = result["registered_districts"]
        assert districts["county_precinct"] == "SS01"
        assert districts["congressional_district"] == "05"
        assert districts["state_senate_district"] == "34"

    def test_no_geocoded_location(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        assert result["primary_geocoded_location"] is None

    def test_with_primary_geocoded_location(self) -> None:
        loc = _make_location(is_primary=True)
        voter = _make_voter(geocoded_locations=[loc])
        result = build_voter_detail_dict(voter)
        geo = result["primary_geocoded_location"]
        assert geo is not None
        assert geo["latitude"] == 33.749
        assert geo["longitude"] == -84.388
        assert geo["source_type"] == "census"
        assert geo["confidence_score"] == 0.95

    def test_with_non_primary_location_excluded(self) -> None:
        loc = _make_location(is_primary=False)
        voter = _make_voter(geocoded_locations=[loc])
        result = build_voter_detail_dict(voter)
        assert result["primary_geocoded_location"] is None

    def test_multiple_locations_picks_primary(self) -> None:
        loc1 = _make_location(is_primary=False)
        loc2 = _make_location(is_primary=True)
        loc2.latitude = 34.0
        voter = _make_voter(geocoded_locations=[loc1, loc2])
        result = build_voter_detail_dict(voter)
        assert result["primary_geocoded_location"]["latitude"] == 34.0

    def test_dates_included(self) -> None:
        voter = _make_voter()
        result = build_voter_detail_dict(voter)
        assert result["registration_date"] == date(2020, 1, 15)
        assert result["last_vote_date"] == date(2024, 11, 5)

    def test_soft_deleted_voter(self) -> None:
        deleted_at = datetime(2025, 1, 1, tzinfo=UTC)
        voter = _make_voter(
            present_in_latest_import=False,
            soft_deleted_at=deleted_at,
        )
        result = build_voter_detail_dict(voter)
        assert result["present_in_latest_import"] is False
        assert result["soft_deleted_at"] == deleted_at


class TestVoterServiceExports:
    """Verify voter service public API is importable."""

    def test_search_voters_callable(self) -> None:
        from voter_api.services.voter_service import search_voters

        assert callable(search_voters)

    def test_get_voter_detail_callable(self) -> None:
        from voter_api.services.voter_service import get_voter_detail

        assert callable(get_voter_detail)

    def test_build_voter_detail_dict_callable(self) -> None:
        from voter_api.services.voter_service import build_voter_detail_dict

        assert callable(build_voter_detail_dict)
