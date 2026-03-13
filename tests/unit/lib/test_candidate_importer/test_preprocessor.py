"""Tests for candidate importer preprocessor."""

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from voter_api.lib.candidate_importer.preprocessor import (
    PreprocessResult,
    preprocess_candidates_csv,
)
from voter_api.lib.district_parser import ParsedDistrict

_HEADER = (
    '"CONTEST NAME","COUNTY","MUNICIPALITY","CANDIDATE NAME",'
    '"CANDIDATE STATUS","POLITICAL PARTY","QUALIFIED DATE",'
    '"INCUMBENT","OCCUPATION","EMAIL ADDRESS","WEBSITE"'
)
_ROW_1 = (
    '"U.S House of Representatives, District 11 (R)","PICKENS","",'
    '"CHRIS MORA","Qualified","Republican","03/02/2026","NO",'
    '"TELECOMMUNICATIONS","campaign@moraforgeorgia.com","MORAFORGEORGIA.COM"'
)
_ROW_2 = (
    '"Governor (R)","","","BRIAN KEMP","Qualified","Republican","03/02/2026","YES","GOVERNOR","","WWW.BRIANKEMP.COM"'
)
_ROW_3 = (
    '"State Senate, District 18 (D)","FULTON","","JANE DOE",'
    '"Withdrew","Democrat","03/01/2026","NO","ATTORNEY",'
    '"jane@example.com",""'
)
_SAMPLE_CSV = f"{_HEADER}\n{_ROW_1}\n{_ROW_2}\n{_ROW_3}\n"

_ELECTION_DATE = date(2026, 5, 19)
_ELECTION_TYPE = "general_primary"


def _make_parsed(
    district_type: str | None,
    district_identifier: str | None = None,
    party: str | None = None,
    county: str | None = None,
    raw: str = "",
) -> ParsedDistrict:
    return ParsedDistrict(
        district_type=district_type,
        district_identifier=district_identifier,
        party=party,
        county=county,
        raw=raw,
    )


def _mock_parse_contest_name(
    text: str,
    county: str | None = None,
    municipality: str | None = None,
) -> ParsedDistrict:
    """Mock parse_contest_name returning known results for test data."""
    lookup: dict[str, ParsedDistrict] = {
        "U.S House of Representatives, District 11 (R)": _make_parsed(
            "congressional",
            "11",
            "Republican",
            raw=text,
        ),
        "Governor (R)": _make_parsed(
            "statewide",
            None,
            "Republican",
            raw=text,
        ),
        "State Senate, District 18 (D)": _make_parsed(
            "state_senate",
            "18",
            "Democrat",
            raw=text,
        ),
    }
    return lookup.get(text, _make_parsed(None, raw=text))


class TestPreprocessCandidatesCsv:
    """Tests for preprocess_candidates_csv."""

    def test_basic_preprocessing(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            result = preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        assert isinstance(result, PreprocessResult)
        assert result.total_records == 3
        assert result.resolved_regex == 3
        assert result.resolved_ai == 0
        assert result.needs_review == 0
        assert result.output_path == output_path
        assert output_path.exists()

    def test_output_jsonl_has_correct_fields(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        lines = output_path.read_text().strip().split("\n")
        assert len(lines) == 3

        first = json.loads(lines[0])
        assert first["election_name"] == "U.S House of Representatives, District 11 (R)"
        assert first["election_date"] == "2026-05-19"
        assert first["election_type"] == "general_primary"
        assert first["candidate_name"] == "CHRIS MORA"
        assert first["party"] == "Republican"
        assert first["filing_status"] == "qualified"
        assert first["is_incumbent"] is False
        assert first["qualified_date"] == "2026-03-02"
        assert first["occupation"] == "TELECOMMUNICATIONS"
        assert first["email"] == "campaign@moraforgeorgia.com"
        assert first["website"] == "https://MORAFORGEORGIA.COM"
        assert first["county"] == "PICKENS"
        assert first["district_type"] == "congressional"
        assert first["district_identifier"] == "11"

    def test_incumbent_parsing(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        lines = output_path.read_text().strip().split("\n")
        first = json.loads(lines[0])
        second = json.loads(lines[1])

        assert first["is_incumbent"] is False  # NO
        assert second["is_incumbent"] is True  # YES

    def test_filing_status_mapping(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        lines = output_path.read_text().strip().split("\n")
        third = json.loads(lines[2])
        assert third["filing_status"] == "withdrawn"  # "Withdrew" -> "withdrawn"

    def test_unresolved_contest_names_marked_for_review(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        def _always_fail(text: str, **kwargs: object) -> ParsedDistrict:
            return _make_parsed(None, raw=text)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_always_fail,
        ):
            result = preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        assert result.needs_review == 3
        assert result.resolved_regex == 0

        lines = output_path.read_text().strip().split("\n")
        for line in lines:
            record = json.loads(line)
            assert record["_needs_manual_review"] is True

    def test_ai_resolution_when_regex_fails(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        def _partial_fail(
            text: str,
            county: str | None = None,
            municipality: str | None = None,
        ) -> ParsedDistrict:
            """Resolve only Governor, leave others unresolved."""
            if "Governor" in text:
                return _make_parsed("statewide", None, "Republican", raw=text)
            return _make_parsed(None, raw=text)

        mock_ai_result = [
            {
                "contest_name": "U.S House of Representatives, District 11 (R)",
                "district_type": "congressional",
                "district_identifier": "11",
                "district_party": "Republican",
            },
            {
                "contest_name": "State Senate, District 18 (D)",
                "district_type": "state_senate",
                "district_identifier": "18",
                "district_party": "Democrat",
            },
        ]

        with (
            patch(
                "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
                side_effect=_partial_fail,
            ),
            patch(
                "voter_api.lib.candidate_importer.preprocessor.resolve_contest_names_batch",
                return_value=mock_ai_result,
            ),
        ):
            result = preprocess_candidates_csv(
                input_path,
                output_path,
                _ELECTION_DATE,
                _ELECTION_TYPE,
                api_key="test-key",
            )

        assert result.resolved_regex == 1  # Governor
        assert result.resolved_ai == 2  # US House + State Senate
        assert result.needs_review == 0

    def test_website_gets_https_prefix(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        lines = output_path.read_text().strip().split("\n")
        first = json.loads(lines[0])
        second = json.loads(lines[1])

        assert first["website"] == "https://MORAFORGEORGIA.COM"
        assert second["website"] == "https://WWW.BRIANKEMP.COM"

    def test_empty_email_and_website_are_none(self, tmp_path: Path) -> None:
        input_path = tmp_path / "candidates.csv"
        output_path = tmp_path / "output.jsonl"
        input_path.write_text(_SAMPLE_CSV)

        with patch(
            "voter_api.lib.candidate_importer.preprocessor.parse_contest_name",
            side_effect=_mock_parse_contest_name,
        ):
            preprocess_candidates_csv(input_path, output_path, _ELECTION_DATE, _ELECTION_TYPE)

        lines = output_path.read_text().strip().split("\n")
        second = json.loads(lines[1])  # BRIAN KEMP has empty email

        assert second["email"] is None
        third = json.loads(lines[2])  # JANE DOE has empty website
        assert third["website"] is None
