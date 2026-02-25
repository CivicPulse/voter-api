"""Tests for the analyzer comparator module."""

from unittest.mock import MagicMock

from voter_api.lib.analyzer.comparator import (
    BOUNDARY_TYPE_TO_VOTER_FIELD,
    compare_boundaries,
    extract_registered_boundaries,
    normalize_for_comparison,
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


class TestNormalizeForComparison:
    """Tests for normalize_for_comparison."""

    def test_strips_leading_zeros_from_numeric_district(self) -> None:
        det, reg = normalize_for_comparison("congressional", "008", "8")
        assert det == "8"
        assert reg == "8"

    def test_strips_leading_zeros_both_sides(self) -> None:
        det, reg = normalize_for_comparison("state_senate", "034", "034")
        assert det == "34"
        assert reg == "34"

    def test_genuine_numeric_mismatch_preserved(self) -> None:
        det, reg = normalize_for_comparison("congressional", "005", "6")
        assert det == "5"
        assert reg == "6"

    def test_non_numeric_district_value_unchanged(self) -> None:
        det, reg = normalize_for_comparison("congressional", "ABC", "ABC")
        assert det == "ABC"
        assert reg == "ABC"

    def test_precinct_fips_prefix_stripped(self) -> None:
        det, reg = normalize_for_comparison("county_precinct", "021HO3", "HO3")
        assert det == "HO3"
        assert reg == "HO3"

    def test_precinct_no_strip_when_suffix_differs(self) -> None:
        det, reg = normalize_for_comparison("county_precinct", "021HO3", "HO4")
        assert det == "021HO3"
        assert reg == "HO4"

    def test_precinct_short_value_unchanged(self) -> None:
        det, reg = normalize_for_comparison("county_precinct", "HO3", "HO3")
        assert det == "HO3"
        assert reg == "HO3"

    def test_municipal_precinct_fips_prefix_stripped(self) -> None:
        det, reg = normalize_for_comparison("municipal_precinct", "060MP1", "MP1")
        assert det == "MP1"
        assert reg == "MP1"

    def test_whitespace_stripped(self) -> None:
        det, reg = normalize_for_comparison("congressional", " 008 ", " 8 ")
        assert det == "8"
        assert reg == "8"

    def test_noop_for_matching_non_numeric_non_precinct(self) -> None:
        """Types that are neither numeric nor precinct pass through unchanged."""
        det, reg = normalize_for_comparison("unknown_type", "ABC", "ABC")
        assert det == "ABC"
        assert reg == "ABC"

    def test_state_house_zero_padding(self) -> None:
        det, reg = normalize_for_comparison("state_house", "042", "42")
        assert det == "42"
        assert reg == "42"


class TestCompareBoundariesNormalization:
    """Integration tests verifying compare_boundaries uses normalization."""

    def test_padded_determined_matches_unpadded_registered(self) -> None:
        """The exact bug: boundary "008" should match voter "8"."""
        determined = {
            "congressional": "008",
            "state_senate": "034",
            "state_house": "042",
        }
        registered = {
            "congressional": "8",
            "state_senate": "34",
            "state_house": "42",
        }
        result = compare_boundaries(determined, registered)
        assert result.match_status == "match"
        assert result.mismatch_details == []

    def test_precinct_fips_prefix_matches(self) -> None:
        """Boundary "021HO3" should match voter "HO3"."""
        determined = {"county_precinct": "021HO3"}
        registered = {"county_precinct": "HO3"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "match"
        assert result.mismatch_details == []

    def test_genuine_mismatch_still_detected(self) -> None:
        """Real mismatches should still be reported with raw values."""
        determined = {"congressional": "005", "county_precinct": "021HO3"}
        registered = {"congressional": "6", "county_precinct": "HO4"}
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-both"
        assert len(result.mismatch_details) == 2
        # Raw values preserved in mismatch_details for debugging
        cong = next(d for d in result.mismatch_details if d["boundary_type"] == "congressional")
        assert cong["determined"] == "005"
        assert cong["registered"] == "6"

    def test_mixed_match_and_mismatch_with_normalization(self) -> None:
        """Some types match after normalization, others genuinely mismatch."""
        determined = {
            "congressional": "008",
            "state_senate": "010",
            "county_precinct": "021HO3",
        }
        registered = {
            "congressional": "8",
            "state_senate": "11",
            "county_precinct": "HO3",
        }
        result = compare_boundaries(determined, registered)
        assert result.match_status == "mismatch-district"
        assert len(result.mismatch_details) == 1
        assert result.mismatch_details[0]["boundary_type"] == "state_senate"
