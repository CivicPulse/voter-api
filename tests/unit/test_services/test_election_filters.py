"""Unit tests for election search/filter utilities and constants."""

from voter_api.services.election_service import (
    _NON_LOCAL_TYPES,
    RACE_CATEGORY_MAP,
    escape_ilike_wildcards,
)


class TestEscapeIlikeWildcards:
    """Tests for the escape_ilike_wildcards utility function."""

    def test_plain_text_unchanged(self) -> None:
        assert escape_ilike_wildcards("hello") == "hello"

    def test_percent_sign_escaped(self) -> None:
        assert escape_ilike_wildcards("100%") == "100\\%"

    def test_underscore_escaped(self) -> None:
        assert escape_ilike_wildcards("District_1") == "District\\_1"

    def test_backslash_escaped_first(self) -> None:
        """Backslash must be escaped before % and _ to avoid double-escaping."""
        assert escape_ilike_wildcards("50%_off\\deal") == "50\\%\\_off\\\\deal"

    def test_empty_string_passthrough(self) -> None:
        assert escape_ilike_wildcards("") == ""

    def test_combined_special_chars(self) -> None:
        assert escape_ilike_wildcards("a\\b%c_d") == "a\\\\b\\%c\\_d"


class TestRaceCategoryMap:
    """Tests for the RACE_CATEGORY_MAP constant and derived _NON_LOCAL_TYPES."""

    def test_map_has_exactly_three_keys(self) -> None:
        assert len(RACE_CATEGORY_MAP) == 3

    def test_federal_maps_to_congressional(self) -> None:
        assert RACE_CATEGORY_MAP["federal"] == ["congressional"]

    def test_state_senate_maps_to_state_senate(self) -> None:
        assert RACE_CATEGORY_MAP["state_senate"] == ["state_senate"]

    def test_state_house_maps_to_state_house(self) -> None:
        assert RACE_CATEGORY_MAP["state_house"] == ["state_house"]

    def test_non_local_types_contains_all_three(self) -> None:
        assert sorted(_NON_LOCAL_TYPES) == ["congressional", "state_house", "state_senate"]
