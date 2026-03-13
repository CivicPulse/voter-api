"""Unit tests for parse_contest_name — Qualified Candidates CSV contest name parsing."""

import pytest

from voter_api.lib.district_parser import ParsedDistrict, parse_contest_name


class TestParseContestNameKnownPatterns:
    """Tests for parse_contest_name covering all observed GA SoS Qualified Candidates patterns."""

    @pytest.mark.parametrize(
        ("text", "expected_type", "expected_id", "expected_party", "county", "municipality", "expected_county"),
        [
            # --- Congressional ---
            (
                "U.S House of Representatives, District 11 (R)",
                "congressional",
                "11",
                "Republican",
                None,
                None,
                None,
            ),
            (
                "U.S House of Representatives, District 11 (D)",
                "congressional",
                "11",
                "Democrat",
                None,
                None,
                None,
            ),
            (
                "U.S House of Representatives, District 3 (R)",
                "congressional",
                "3",
                "Republican",
                None,
                None,
                None,
            ),
            (
                "U.S. House of Representatives, District 7 (D)",
                "congressional",
                "7",
                "Democrat",
                None,
                None,
                None,
            ),
            # --- US Senate ---
            (
                "U.S Senate (R)",
                "us_senate",
                None,
                "Republican",
                None,
                None,
                None,
            ),
            (
                "U.S. Senate (D)",
                "us_senate",
                None,
                "Democrat",
                None,
                None,
                None,
            ),
            # --- State Senate ---
            (
                "State Senate, District 23 (R)",
                "state_senate",
                "23",
                "Republican",
                None,
                None,
                None,
            ),
            (
                "State Senate, District 1 (D)",
                "state_senate",
                "1",
                "Democrat",
                None,
                None,
                None,
            ),
            # --- State House ---
            (
                "State House, District 4 (R)",
                "state_house",
                "4",
                "Republican",
                None,
                None,
                None,
            ),
            (
                "State House, District 130 (D)",
                "state_house",
                "130",
                "Democrat",
                None,
                None,
                None,
            ),
            # --- PSC ---
            (
                "Public Service Commission, District 2 (R)",
                "psc",
                "2",
                "Republican",
                None,
                None,
                None,
            ),
            (
                "PSC, District 3 (D)",
                "psc",
                "3",
                "Democrat",
                None,
                None,
                None,
            ),
            # --- Statewide offices ---
            ("Governor (R)", "statewide", None, "Republican", None, None, None),
            ("Governor (D)", "statewide", None, "Democrat", None, None, None),
            ("Lieutenant Governor (R)", "statewide", None, "Republican", None, None, None),
            ("Lieutenant Governor (D)", "statewide", None, "Democrat", None, None, None),
            ("Secretary of State (R)", "statewide", None, "Republican", None, None, None),
            ("Attorney General (R)", "statewide", None, "Republican", None, None, None),
            ("Commissioner of Agriculture (R)", "statewide", None, "Republican", None, None, None),
            ("Commissioner of Insurance (R)", "statewide", None, "Republican", None, None, None),
            ("Commissioner of Labor (R)", "statewide", None, "Republican", None, None, None),
            ("State School Superintendent (R)", "statewide", None, "Republican", None, None, None),
            # --- Judicial ---
            (
                "Supreme Court Justice - Seat 2 (NP)",
                "judicial",
                "2",
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "Court of Appeals Judge, Seat 12 (NP)",
                "judicial",
                "12",
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "Superior Court Judge, Blue Ridge Judicial Circuit (NP)",
                "judicial",
                None,
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "District Attorney, Appalachian Judicial Circuit (NP)",
                "judicial",
                None,
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "Solicitor General, State Court of DeKalb County (NP)",
                "judicial",
                None,
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "Judge, State Court of Chatham County (NP)",
                "judicial",
                None,
                "Nonpartisan",
                None,
                None,
                None,
            ),
            (
                "Chief Magistrate, Magistrate Court of DeKalb County (NP)",
                "judicial",
                None,
                "Nonpartisan",
                None,
                None,
                None,
            ),
            # --- Board of Education ---
            (
                "Board of Education, District 2 (R)",
                "board_of_education",
                "2",
                "Republican",
                "Fulton",
                None,
                "Fulton",
            ),
            (
                "Board of Education, Post 2 (NP)",
                "board_of_education",
                "2",
                "Nonpartisan",
                "DeKalb",
                None,
                "DeKalb",
            ),
            (
                "School Board, District 3 (NP)",
                "board_of_education",
                "3",
                "Nonpartisan",
                "Chatham",
                None,
                "Chatham",
            ),
            # --- County Commission ---
            (
                "County Commission Chairman (R)",
                "county_commission",
                None,
                "Republican",
                "Bibb",
                None,
                "Bibb",
            ),
            (
                "County Commissioner, District 1 (R)",
                "county_commission",
                "1",
                "Republican",
                "Fulton",
                None,
                "Fulton",
            ),
            (
                "County Commissioner, Post 1 (R)",
                "county_commission",
                "1",
                "Republican",
                "Clayton",
                None,
                "Clayton",
            ),
            (
                "Chair, Board of Commissioners (R)",
                "county_commission",
                None,
                "Republican",
                "Gwinnett",
                None,
                "Gwinnett",
            ),
            # --- County Office ---
            (
                "Clerk of Superior Court (R)",
                "county_office",
                None,
                "Republican",
                "Fulton",
                None,
                "Fulton",
            ),
            (
                "Sheriff (R)",
                "county_office",
                None,
                "Republican",
                "DeKalb",
                None,
                "DeKalb",
            ),
            (
                "Tax Commissioner (R)",
                "county_office",
                None,
                "Republican",
                "Bibb",
                None,
                "Bibb",
            ),
            (
                "Coroner (R)",
                "county_office",
                None,
                "Republican",
                "Clayton",
                None,
                "Clayton",
            ),
            (
                "Probate Judge (R)",
                "county_office",
                None,
                "Republican",
                "Chatham",
                None,
                "Chatham",
            ),
            (
                "Surveyor (NP)",
                "county_office",
                None,
                "Nonpartisan",
                "Cobb",
                None,
                "Cobb",
            ),
            # --- Municipal ---
            (
                "Mayor (NP)",
                "municipal",
                None,
                "Nonpartisan",
                None,
                "Atlanta",
                "Atlanta",
            ),
            (
                "City Council, Post 1 (NP)",
                "city_council",
                "1",
                "Nonpartisan",
                None,
                "Savannah",
                "Savannah",
            ),
            (
                "City Council, Ward 2 (NP)",
                "city_council",
                "2",
                "Nonpartisan",
                None,
                "Macon",
                "Macon",
            ),
            (
                "City Council, District 3 (NP)",
                "city_council",
                "3",
                "Nonpartisan",
                None,
                "Augusta",
                "Augusta",
            ),
        ],
        ids=[
            "congressional-11-R",
            "congressional-11-D",
            "congressional-3-R",
            "congressional-dotted-7-D",
            "us-senate-R",
            "us-senate-dotted-D",
            "state-senate-23-R",
            "state-senate-1-D",
            "state-house-4-R",
            "state-house-130-D",
            "psc-2-R",
            "psc-abbrev-3-D",
            "statewide-governor-R",
            "statewide-governor-D",
            "statewide-lt-governor-R",
            "statewide-lt-governor-D",
            "statewide-sos-R",
            "statewide-ag-R",
            "statewide-agriculture-R",
            "statewide-insurance-R",
            "statewide-labor-R",
            "statewide-school-supt-R",
            "judicial-supreme-court-seat-2",
            "judicial-court-of-appeals-seat-12",
            "judicial-superior-court",
            "judicial-district-attorney",
            "judicial-solicitor-general",
            "judicial-judge-state-court",
            "judicial-chief-magistrate",
            "boe-district-2-R",
            "boe-post-2-NP",
            "school-board-district-3",
            "county-commission-chairman",
            "county-commissioner-district-1",
            "county-commissioner-post-1",
            "chair-board-of-commissioners",
            "county-office-clerk",
            "county-office-sheriff",
            "county-office-tax-commissioner",
            "county-office-coroner",
            "county-office-probate-judge",
            "county-office-surveyor",
            "municipal-mayor",
            "municipal-city-council-post",
            "municipal-city-council-ward",
            "municipal-city-council-district",
        ],
    )
    def test_known_patterns(
        self,
        text: str,
        expected_type: str,
        expected_id: str | None,
        expected_party: str | None,
        county: str | None,
        municipality: str | None,
        expected_county: str | None,
    ) -> None:
        result = parse_contest_name(text, county=county, municipality=municipality)
        assert result.district_type == expected_type
        assert result.district_identifier == expected_id
        assert result.party == expected_party
        assert result.county == expected_county
        assert result.raw == text


class TestParseContestNamePartyExtraction:
    """Tests for party abbreviation extraction and mapping."""

    @pytest.mark.parametrize(
        ("suffix", "expected_party"),
        [
            ("(R)", "Republican"),
            ("(D)", "Democrat"),
            ("(NP)", "Nonpartisan"),
            ("(L)", "Libertarian"),
            ("(I)", "Independent"),
        ],
        ids=["republican", "democrat", "nonpartisan", "libertarian", "independent"],
    )
    def test_party_abbreviations(self, suffix: str, expected_party: str) -> None:
        result = parse_contest_name(f"Governor {suffix}")
        assert result.party == expected_party

    def test_unknown_party_abbreviation_preserved(self) -> None:
        """Unknown party abbreviations are returned as-is."""
        result = parse_contest_name("Governor (X)")
        assert result.party == "X"

    def test_no_party_suffix(self) -> None:
        """Contest names without a party suffix return party=None."""
        result = parse_contest_name("Governor")
        assert result.party is None


class TestParseContestNameDistrictExtraction:
    """Tests for district/seat/post/ward number extraction."""

    @pytest.mark.parametrize(
        ("text", "expected_id"),
        [
            ("State Senate, District 23 (R)", "23"),
            ("Supreme Court Justice - Seat 2 (NP)", "2"),
            ("County Commissioner, Post 1 (R)", "1"),
            ("City Council, Ward 2 (NP)", "2"),
            ("Some Office, Division 4 (R)", "4"),
        ],
        ids=["district", "seat", "post", "ward", "division"],
    )
    def test_identifier_keywords(self, text: str, expected_id: str) -> None:
        result = parse_contest_name(text)
        assert result.district_identifier == expected_id

    def test_no_district_number(self) -> None:
        result = parse_contest_name("Governor (R)")
        assert result.district_identifier is None


class TestParseContestNameCountyParameter:
    """Tests for county/municipality parameter propagation."""

    def test_county_commission_gets_county(self) -> None:
        result = parse_contest_name("County Commissioner, District 1 (R)", county="Fulton")
        assert result.county == "Fulton"

    def test_county_office_gets_county(self) -> None:
        result = parse_contest_name("Sheriff (R)", county="DeKalb")
        assert result.county == "DeKalb"

    def test_board_of_education_gets_county(self) -> None:
        result = parse_contest_name("Board of Education, District 2 (R)", county="Cobb")
        assert result.county == "Cobb"

    def test_municipal_gets_municipality(self) -> None:
        result = parse_contest_name("Mayor (NP)", municipality="Atlanta")
        assert result.county == "Atlanta"

    def test_statewide_ignores_county(self) -> None:
        result = parse_contest_name("Governor (R)", county="Fulton")
        assert result.county is None

    def test_congressional_ignores_county(self) -> None:
        result = parse_contest_name("U.S House of Representatives, District 11 (R)", county="Fulton")
        assert result.county is None


class TestParseContestNameFallback:
    """Tests for unrecognized contest names."""

    @pytest.mark.parametrize(
        "text",
        [
            "Some Unknown Office (R)",
            "Water District Board, Seat 3 (NP)",
            "",
        ],
        ids=["unknown-office", "water-district", "empty-string"],
    )
    def test_unrecognized_returns_none_type(self, text: str) -> None:
        result = parse_contest_name(text)
        assert result.district_type is None
        assert result.raw == text

    def test_unrecognized_still_extracts_party(self) -> None:
        result = parse_contest_name("Some Unknown Office (R)")
        assert result.party == "Republican"

    def test_unrecognized_still_extracts_district_id(self) -> None:
        result = parse_contest_name("Water District Board, Seat 3 (NP)")
        assert result.district_identifier == "3"
        assert result.party == "Nonpartisan"


class TestParseContestNameReturnType:
    """Tests for return type correctness."""

    def test_returns_parsed_district(self) -> None:
        result = parse_contest_name("Governor (R)")
        assert isinstance(result, ParsedDistrict)

    def test_returns_frozen_dataclass(self) -> None:
        result = parse_contest_name("Governor (R)")
        with pytest.raises(AttributeError):
            result.district_type = "other"  # type: ignore[misc]
