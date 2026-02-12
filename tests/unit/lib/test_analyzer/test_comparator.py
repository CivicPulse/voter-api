"""Tests for the analyzer comparator module."""

from unittest.mock import MagicMock

from voter_api.lib.analyzer.comparator import (
    BOUNDARY_TYPE_TO_VOTER_FIELD,
    compare_boundaries,
    extract_registered_boundaries,
)


def _make_voter(**kwargs: str | None) -> MagicMock:
    """Create a mock voter with optional district attributes."""
    voter = MagicMock()
    # Set all district fields to None by default
    for field_name in BOUNDARY_TYPE_TO_VOTER_FIELD.values():
        setattr(voter, field_name, None)
    # Override with provided values
    for key, value in kwargs.items():
        setattr(voter, key, value)
    return voter


class TestExtractRegisteredBoundaries:
    """Tests for extract_registered_boundaries."""

    def test_extracts_non_null_fields(self) -> None:
        voter = _make_voter(
            congressional_district="05",
            state_senate_district="34",
            county_precinct="SS01",
        )
        result = extract_registered_boundaries(voter)
        assert result == {
            "congressional": "05",
            "state_senate": "34",
            "county_precinct": "SS01",
        }

    def test_ignores_null_fields(self) -> None:
        voter = _make_voter(congressional_district="05")
        result = extract_registered_boundaries(voter)
        assert result == {"congressional": "05"}
        assert "state_senate" not in result

    def test_ignores_empty_strings(self) -> None:
        voter = _make_voter(congressional_district="", state_senate_district="  ")
        result = extract_registered_boundaries(voter)
        assert result == {}

    def test_strips_whitespace(self) -> None:
        voter = _make_voter(congressional_district="  05  ")
        result = extract_registered_boundaries(voter)
        assert result == {"congressional": "05"}

    def test_empty_voter(self) -> None:
        voter = _make_voter()
        result = extract_registered_boundaries(voter)
        assert result == {}


class TestCompareBoundaries:
    """Tests for compare_boundaries."""

    def test_match_all_same(self) -> None:
        determined = {"congressional": "05", "county_precinct": "SS01"}
        registered = {"congressional": "05", "county_precinct": "SS01"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "match"
        assert result.mismatch_details == []

    def test_mismatch_district(self) -> None:
        determined = {"congressional": "05", "county_precinct": "SS01"}
        registered = {"congressional": "06", "county_precinct": "SS01"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-district"
        assert len(result.mismatch_details) == 1
        assert result.mismatch_details[0]["boundary_type"] == "congressional"
        assert result.mismatch_details[0]["registered"] == "06"
        assert result.mismatch_details[0]["determined"] == "05"

    def test_mismatch_precinct(self) -> None:
        determined = {"congressional": "05", "county_precinct": "SS02"}
        registered = {"congressional": "05", "county_precinct": "SS01"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-precinct"
        assert len(result.mismatch_details) == 1
        assert result.mismatch_details[0]["boundary_type"] == "county_precinct"

    def test_mismatch_both(self) -> None:
        determined = {"congressional": "05", "county_precinct": "SS02"}
        registered = {"congressional": "06", "county_precinct": "SS01"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-both"
        assert len(result.mismatch_details) == 2

    def test_unable_to_analyze_empty_determined(self) -> None:
        determined: dict[str, str] = {}
        registered = {"congressional": "05"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "unable-to-analyze"
        assert result.mismatch_details == []

    def test_extra_determined_types_ignored(self) -> None:
        """Boundary types only in determined but not registered are not mismatches."""
        determined = {"congressional": "05", "state_house": "42"}
        registered = {"congressional": "05"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "match"

    def test_extra_registered_types_ignored(self) -> None:
        """Boundary types only in registered but not determined are not mismatches."""
        determined = {"congressional": "05"}
        registered = {"congressional": "05", "state_house": "42"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "match"

    def test_mismatch_details_sorted_by_type(self) -> None:
        determined = {
            "state_senate": "10",
            "congressional": "05",
        }
        registered = {
            "state_senate": "11",
            "congressional": "06",
        }
        result = compare_boundaries(determined, registered)
        types = [d["boundary_type"] for d in result.mismatch_details]
        assert types == ["congressional", "state_senate"]

    def test_multiple_district_mismatches(self) -> None:
        determined = {
            "congressional": "05",
            "state_senate": "10",
            "state_house": "42",
        }
        registered = {
            "congressional": "06",
            "state_senate": "11",
            "state_house": "43",
        }
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-district"
        assert len(result.mismatch_details) == 3

    def test_both_empty(self) -> None:
        result = compare_boundaries({}, {})
        assert result.match_status == "unable-to-analyze"

    def test_result_contains_all_boundaries(self) -> None:
        determined = {"congressional": "05"}
        registered = {"congressional": "05", "state_senate": "34"}
        result = compare_boundaries(determined, registered)
        assert result.determined_boundaries == determined
        assert result.registered_boundaries == registered
