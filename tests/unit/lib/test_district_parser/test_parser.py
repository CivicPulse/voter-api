"""Unit tests for district parser library."""

import pytest

from voter_api.lib.district_parser import (
    PSC_DISTRICT_COUNTIES,
    ParsedDistrict,
    get_psc_district_for_county,
    pad_district_identifier,
    parse_election_district,
)


class TestParseElectionDistrict:
    """Tests for parse_election_district covering all observed GA SoS patterns."""

    @pytest.mark.parametrize(
        ("district_text", "expected_type", "expected_id", "expected_party", "expected_county"),
        [
            # State Senate variants
            ("State Senate - District 18", "state_senate", "18", None, None),
            ("State Senate District 18", "state_senate", "18", None, None),
            ("State Senate - District 53", "state_senate", "53", None, None),
            ("State Senate - District 35", "state_senate", "35", None, None),
            # State House variants
            (
                "State House of Representatives - District 94",
                "state_house",
                "94",
                None,
                None,
            ),
            (
                "State House of Representatives - District 130",
                "state_house",
                "130",
                None,
                None,
            ),
            (
                "State House of Representatives - District 23",
                "state_house",
                "23",
                None,
                None,
            ),
            (
                "State House of Representatives - District 106",
                "state_house",
                "106",
                None,
                None,
            ),
            (
                "State House of Representatives - District 121",
                "state_house",
                "121",
                None,
                None,
            ),
            # Congressional
            (
                "US House of Representatives - District 14",
                "congressional",
                "14",
                None,
                None,
            ),
            # PSC without party
            ("PSC - District 2", "psc", "2", None, None),
            ("PSC - District 3", "psc", "3", None, None),
            # PSC with party
            ("PSC - District 3 - Dem", "psc", "3", "Dem", None),
            ("PSC - District 2 - Rep", "psc", "2", "Rep", None),
            ("PSC - District 2 - Dem", "psc", "2", "Dem", None),
            ("PSC - District 3 - Rep", "psc", "3", "Rep", None),
            # County Commission — county field must be populated
            ("Bibb County Commission District 5", "county_commission", "5", None, "Bibb"),
            ("Clayton County Commission District 3", "county_commission", "3", None, "Clayton"),
            (
                "Fulton County Commission District 12",
                "county_commission",
                "12",
                None,
                "Fulton",
            ),
            # Special prefix stripped
            ("Special State Senate - District 21", "state_senate", "21", None, None),
            # Spanish translation stripped
            (
                "State House of Representatives - District 94/ Para la Cámara de Representantes del Estado Distrito 94",
                "state_house",
                "94",
                None,
                None,
            ),
            (
                "State House of Representatives - District 106/ Para Representante "
                "Estatal ante la Asamblea General, Distrito 106",
                "state_house",
                "106",
                None,
                None,
            ),
        ],
        ids=[
            "senate-dash",
            "senate-no-dash",
            "senate-53",
            "senate-35",
            "house-94",
            "house-130",
            "house-23",
            "house-106",
            "house-121",
            "congressional-14",
            "psc-2",
            "psc-3",
            "psc-3-dem",
            "psc-2-rep",
            "psc-2-dem",
            "psc-3-rep",
            "county-commission-bibb-5",
            "county-commission-clayton-3",
            "county-commission-fulton-12",
            "special-senate-21",
            "spanish-house-94",
            "spanish-house-106",
        ],
    )
    def test_known_patterns(
        self,
        district_text: str,
        expected_type: str,
        expected_id: str,
        expected_party: str | None,
        expected_county: str | None,
    ) -> None:
        result = parse_election_district(district_text)
        assert result.district_type == expected_type
        assert result.district_identifier == expected_id
        assert result.party == expected_party
        assert result.county == expected_county
        assert result.raw == district_text

    @pytest.mark.parametrize(
        "district_text",
        [
            "Statewide",
            "Unknown Format",
            "",
            "Something Else - District 5",
        ],
    )
    def test_unknown_format_returns_none_fields(self, district_text: str) -> None:
        result = parse_election_district(district_text)
        assert result.district_type is None
        assert result.district_identifier is None
        assert result.party is None
        assert result.county is None
        assert result.raw == district_text

    def test_returns_frozen_dataclass(self) -> None:
        result = parse_election_district("State Senate - District 18")
        assert isinstance(result, ParsedDistrict)
        with pytest.raises(AttributeError):
            result.district_type = "other"  # type: ignore[misc]


class TestPadDistrictIdentifier:
    """Tests for zero-padding utility."""

    @pytest.mark.parametrize(
        ("identifier", "expected"),
        [
            ("18", "018"),
            ("3", "003"),
            ("130", "130"),
            ("1", "001"),
            ("94", "094"),
            ("14", "014"),
        ],
    )
    def test_default_width(self, identifier: str, expected: str) -> None:
        assert pad_district_identifier(identifier) == expected

    def test_custom_width(self) -> None:
        assert pad_district_identifier("3", width=5) == "00003"

    def test_already_padded(self) -> None:
        assert pad_district_identifier("018") == "018"

    def test_overflow_not_truncated(self) -> None:
        """Identifiers longer than width are returned as-is (no truncation)."""
        assert pad_district_identifier("1234", width=3) == "1234"


class TestGetPscDistrictForCounty:
    """Tests for PSC district lookup by county name."""

    @pytest.mark.parametrize(
        ("county", "expected_district"),
        [
            # District 1 counties
            ("Chatham", "1"),
            ("Lowndes", "1"),
            ("Richmond", "1"),
            # District 2 counties
            ("Bibb", "2"),
            ("Muscogee", "2"),
            ("Houston", "2"),
            # District 3 counties
            ("DeKalb", "3"),
            ("Gwinnett", "3"),
            ("Clayton", "3"),
            # District 4 counties
            ("Hall", "4"),
            ("Floyd", "4"),
            ("Whitfield", "4"),
            # District 5 counties
            ("Fulton", "5"),
            ("Cobb", "5"),
            ("Forsyth", "5"),
        ],
        ids=[
            "d1-chatham",
            "d1-lowndes",
            "d1-richmond",
            "d2-bibb",
            "d2-muscogee",
            "d2-houston",
            "d3-dekalb",
            "d3-gwinnett",
            "d3-clayton",
            "d4-hall",
            "d4-floyd",
            "d4-whitfield",
            "d5-fulton",
            "d5-cobb",
            "d5-forsyth",
        ],
    )
    def test_known_counties(self, county: str, expected_district: str) -> None:
        assert get_psc_district_for_county(county) == expected_district

    def test_unknown_county_returns_none(self) -> None:
        assert get_psc_district_for_county("Atlantis") is None

    def test_empty_string_returns_none(self) -> None:
        assert get_psc_district_for_county("") is None

    @pytest.mark.parametrize(
        "county",
        ["chatham", "CHATHAM", "Chatham", "  Chatham  ", "chatham  "],
        ids=["lower", "upper", "title", "padded", "lower-trailing"],
    )
    def test_case_and_whitespace_insensitive(self, county: str) -> None:
        assert get_psc_district_for_county(county) == "1"

    def test_multi_word_county(self) -> None:
        """Multi-word county names like 'Jeff Davis' are matched correctly."""
        assert get_psc_district_for_county("Jeff Davis") == "1"
        assert get_psc_district_for_county("Ben Hill") == "1"
        assert get_psc_district_for_county("North Fulton") == "5"

    def test_all_five_districts_covered(self) -> None:
        """Every district has at least one county."""
        for district_id in ("1", "2", "3", "4", "5"):
            assert district_id in PSC_DISTRICT_COUNTIES
            assert len(PSC_DISTRICT_COUNTIES[district_id]) > 0
