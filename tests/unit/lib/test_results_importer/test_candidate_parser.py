"""Unit tests for candidate name and party parsing."""

from voter_api.lib.results_importer.candidate_parser import (
    normalize_party,
    parse_candidate_name,
)


class TestNormalizeParty:
    def test_republican(self):
        assert normalize_party("Rep") == "Republican"
        assert normalize_party("REP") == "Republican"
        assert normalize_party("rep") == "Republican"

    def test_democrat(self):
        assert normalize_party("Dem") == "Democrat"
        assert normalize_party("DEM") == "Democrat"

    def test_independent(self):
        assert normalize_party("I") == "Independent"
        assert normalize_party("Ind") == "Independent"

    def test_libertarian(self):
        assert normalize_party("Lib") == "Libertarian"

    def test_nonpartisan(self):
        assert normalize_party("NP") == "Nonpartisan"

    def test_empty_returns_none(self):
        assert normalize_party("") is None
        assert normalize_party("  ") is None

    def test_unknown_returns_none(self):
        assert normalize_party("XYZ") is None


class TestParseCandidateName:
    def test_simple_name_with_party(self):
        result = parse_candidate_name("Bill Fincher (Rep)", "Rep")
        assert result.full_name == "Bill Fincher"
        assert result.party == "Republican"
        assert result.is_incumbent is False

    def test_incumbent_with_party(self):
        result = parse_candidate_name("Tim Echols (I) (Rep)", "Rep")
        assert result.full_name == "Tim Echols"
        assert result.party == "Republican"
        assert result.is_incumbent is True

    def test_incumbent_only(self):
        result = parse_candidate_name("Jane Smith (I)", "Dem")
        assert result.full_name == "Jane Smith"
        assert result.is_incumbent is True

    def test_no_markers(self):
        result = parse_candidate_name("John Doe", "")
        assert result.full_name == "John Doe"
        assert result.party is None
        assert result.is_incumbent is False

    def test_party_from_field_not_parenthetical(self):
        # politicalParty field is authoritative
        result = parse_candidate_name("Jane Smith (Dem)", "Rep")
        assert result.party == "Republican"

    def test_democrat_marker(self):
        result = parse_candidate_name("Scott Sanders (Dem)", "Dem")
        assert result.full_name == "Scott Sanders"
        assert result.party == "Democrat"
