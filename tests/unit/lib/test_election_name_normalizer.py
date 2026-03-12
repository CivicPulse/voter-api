"""Tests for election name normalization."""

import pytest

from voter_api.lib.election_name_normalizer import normalize_election_name


class TestNormalizeElectionName:
    """Tests for normalize_election_name()."""

    def test_en_dash_replaced_with_hyphen(self) -> None:
        """En-dashes (\u2013) should be replaced with hyphens."""
        result = normalize_election_name("General Election \u2013 2024")
        assert "\u2013" not in result
        assert result == "General Election - 2024"

    def test_em_dash_replaced_with_hyphen(self) -> None:
        """Em-dashes (\u2014) should be replaced with hyphens."""
        result = normalize_election_name("Primary \u2014 Runoff")
        assert "\u2014" not in result
        assert result == "Primary - Runoff"

    def test_full_month_name_abbreviated(self) -> None:
        """Full month names should be shortened to 3-letter abbreviations."""
        result = normalize_election_name("January 5, 2021 General Election")
        assert result == "Jan 05, 2021 General Election"

    def test_all_months_abbreviated(self) -> None:
        """All 12 month names should be abbreviated."""
        months = [
            ("January", "Jan"),
            ("February", "Feb"),
            ("March", "Mar"),
            ("April", "Apr"),
            ("June", "Jun"),
            ("July", "Jul"),
            ("August", "Aug"),
            ("September", "Sep"),
            ("October", "Oct"),
            ("November", "Nov"),
            ("December", "Dec"),
        ]
        for full, abbr in months:
            result = normalize_election_name(f"{full} 15, 2024")
            assert result.startswith(abbr), f"Expected {full} -> {abbr}, got {result}"

    def test_may_stays_unchanged(self) -> None:
        """May is already 3 letters and should stay unchanged."""
        result = normalize_election_name("May 15, 2024 Primary")
        assert result == "May 15, 2024 Primary"

    def test_single_digit_day_zero_padded(self) -> None:
        """Single-digit days after month abbreviations should be zero-padded."""
        result = normalize_election_name("Nov 3, 2020 General Election")
        assert result == "Nov 03, 2020 General Election"

    def test_double_digit_day_unchanged(self) -> None:
        """Double-digit days should not be modified."""
        result = normalize_election_name("Nov 15, 2020 General Election")
        assert result == "Nov 15, 2020 General Election"

    def test_gen_expanded_to_general(self) -> None:
        """Abbreviation 'Gen' should expand to 'General'."""
        result = normalize_election_name("Nov 03, 2020 Gen Election")
        assert result == "Nov 03, 2020 General Election"

    def test_prim_expanded_to_primary(self) -> None:
        """Abbreviation 'Prim' should expand to 'Primary'."""
        result = normalize_election_name("May 24, 2022 Prim Runoff")
        assert result == "May 24, 2022 Primary Runoff"

    def test_elec_expanded_to_election(self) -> None:
        """Abbreviation 'Elec' should expand to 'Election'."""
        result = normalize_election_name("Nov 03, 2020 General Elec")
        assert result == "Nov 03, 2020 General Election"

    def test_spec_expanded_to_special(self) -> None:
        """Abbreviation 'Spec' should expand to 'Special'."""
        result = normalize_election_name("Spec Election - District 5")
        assert result == "Special Election - District 5"

    def test_multiple_spaces_collapsed(self) -> None:
        """Multiple consecutive spaces should be collapsed to one."""
        result = normalize_election_name("General   Election    2024")
        assert result == "General Election 2024"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace should be removed."""
        result = normalize_election_name("  General Election 2024  ")
        assert result == "General Election 2024"

    def test_empty_string_returns_empty(self) -> None:
        """Empty string should be returned unchanged."""
        assert normalize_election_name("") == ""

    def test_none_returns_none(self) -> None:
        """None should be returned as-is (falsy check)."""
        assert normalize_election_name(None) is None  # type: ignore[arg-type]

    def test_already_normalized_stays_unchanged(self) -> None:
        """An already-normalized name should not change."""
        name = "Nov 03, 2020 General Election - US Senate"
        assert normalize_election_name(name) == name

    def test_combined_transformations(self) -> None:
        """Multiple transformations should be applied together."""
        raw = "  January 5, 2021  Gen  Elec \u2013 US Senate  "
        expected = "Jan 05, 2021 General Election - US Senate"
        assert normalize_election_name(raw) == expected

    def test_abbreviation_not_expanded_in_middle_of_word(self) -> None:
        """Abbreviation expansion should be word-boundary aware."""
        result = normalize_election_name("General Election - Genesis District")
        assert result == "General Election - Genesis District"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("November 8, 2022 General Election", "Nov 08, 2022 General Election"),
            ("June 9, 2020 Prim Runoff", "Jun 09, 2020 Primary Runoff"),
            ("Spec Elec \u2013 HD 34", "Special Election - HD 34"),
        ],
    )
    def test_parametrized_normalization(self, raw: str, expected: str) -> None:
        """Parametrized tests for various normalization scenarios."""
        assert normalize_election_name(raw) == expected
