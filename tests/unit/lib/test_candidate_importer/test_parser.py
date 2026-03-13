"""Tests for candidate importer JSONL parser."""

import json
from datetime import date
from pathlib import Path

from voter_api.lib.candidate_importer.parser import parse_candidate_import_jsonl


def _make_record(
    name: str = "Governor (R)",
    election_date: str = "2026-05-19",
    candidate: str = "BRIAN KEMP",
    **kwargs: object,
) -> dict:
    """Build a minimal valid record dict."""
    rec = {
        "election_name": name,
        "election_date": election_date,
        "candidate_name": candidate,
    }
    rec.update(kwargs)
    return rec


def _write_jsonl(path: Path, records: list[dict]) -> None:
    """Write records as JSONL to a file."""
    with path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


class TestParseValidJsonl:
    """Tests for parsing valid JSONL files."""

    def test_parse_single_record(self, tmp_path: Path) -> None:
        records = [_make_record()]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert len(batches) == 1
        assert len(batches[0]) == 1
        assert batches[0][0]["candidate_name"] == "BRIAN KEMP"

    def test_date_parsed_to_date_object(self, tmp_path: Path) -> None:
        records = [_make_record()]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert batches[0][0]["election_date"] == date(2026, 5, 19)

    def test_qualified_date_parsed(self, tmp_path: Path) -> None:
        records = [_make_record(qualified_date="2026-03-02")]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert batches[0][0]["qualified_date"] == date(2026, 3, 2)

    def test_multiple_records(self, tmp_path: Path) -> None:
        records = [_make_record(candidate=f"CANDIDATE {i}") for i in range(5)]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert len(batches) == 1
        assert len(batches[0]) == 5


class TestBatching:
    """Tests for batch size handling."""

    def test_exact_batch_size(self, tmp_path: Path) -> None:
        records = [_make_record(candidate=f"C{i}") for i in range(3)]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl", batch_size=3))
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_multiple_batches(self, tmp_path: Path) -> None:
        records = [_make_record(candidate=f"C{i}") for i in range(10)]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl", batch_size=3))
        assert len(batches) == 4
        assert len(batches[0]) == 3
        assert len(batches[1]) == 3
        assert len(batches[2]) == 3
        assert len(batches[3]) == 1

    def test_batch_size_one(self, tmp_path: Path) -> None:
        records = [_make_record(candidate=f"C{i}") for i in range(3)]
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl", batch_size=1))
        assert len(batches) == 3


class TestValidationErrors:
    """Tests for validation error handling during parsing."""

    def test_missing_required_field_sets_parse_error(self, tmp_path: Path) -> None:
        records = [{"election_name": "Governor (R)"}]  # missing date and candidate
        _write_jsonl(tmp_path / "test.jsonl", records)

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert len(batches) == 1
        assert "_parse_error" in batches[0][0]

    def test_invalid_json_sets_parse_error(self, tmp_path: Path) -> None:
        with (tmp_path / "test.jsonl").open("w") as f:
            f.write("this is not json\n")

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert len(batches) == 1
        assert "_parse_error" in batches[0][0]
        assert "Invalid JSON" in batches[0][0]["_parse_error"]

    def test_non_dict_json_sets_parse_error(self, tmp_path: Path) -> None:
        with (tmp_path / "test.jsonl").open("w") as f:
            f.write("[1, 2, 3]\n")

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        assert len(batches) == 1
        assert "_parse_error" in batches[0][0]
        assert "Expected JSON object" in batches[0][0]["_parse_error"]

    def test_empty_lines_are_skipped(self, tmp_path: Path) -> None:
        with (tmp_path / "test.jsonl").open("w") as f:
            f.write(json.dumps(_make_record()) + "\n")
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps(_make_record(candidate="OTHER")) + "\n")

        batches = list(parse_candidate_import_jsonl(tmp_path / "test.jsonl"))
        all_records = [r for batch in batches for r in batch]
        assert len(all_records) == 2
