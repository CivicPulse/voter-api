"""Unit tests for the converter JSONL writer.

Tests cover conversion of ParseResult objects to JSONL-ready records
and writing validated records to JSONL files.
"""

import json
from pathlib import Path

from voter_api.lib.converter.types import ContestData, FileType, ParseResult
from voter_api.lib.converter.writer import parse_result_to_records, write_jsonl
from voter_api.schemas.jsonl.election_event import ElectionEventJSONL


class TestParseResultToRecords:
    """Tests for converting ParseResult to JSONL-ready dicts."""

    def test_overview_to_election_event_record(self) -> None:
        """Overview ParseResult produces an ElectionEventJSONL record."""
        result = ParseResult(
            file_path=Path("2026-05-19-general-primary.md"),
            file_type=FileType.OVERVIEW,
            metadata={
                "ID": "550e8400-e29b-41d4-a716-446655440000",
                "Format Version": "1",
                "Name (SOS)": "May 19, 2026 General Primary",
                "Date": "2026-05-19",
                "Type": "general_primary",
                "Stage": "election",
            },
            heading="May 19, 2026 \u2014 General and Primary Election",
            calendar={
                "Registration Deadline": "2026-04-21",
                "Early Voting Start": "2026-04-27",
            },
        )

        def mock_resolver(body_id: str, county_refs: dict) -> str | None:
            return None

        records = parse_result_to_records(result, mock_resolver)
        assert len(records) == 1
        rec = records[0]
        assert rec.errors == []
        assert len(rec.records) == 1
        record = rec.records[0]
        assert record["id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert record["event_type"] == "general_primary"
        assert record["event_date"] == "2026-05-19"

    def test_single_contest_to_election_record(self) -> None:
        """Single-contest ParseResult produces ElectionJSONL records."""
        result = ParseResult(
            file_path=Path("2026-05-19-governor.md"),
            file_type=FileType.SINGLE_CONTEST,
            metadata={
                "ID": "660e8400-e29b-41d4-a716-446655440001",
                "Format Version": "1",
                "Election": "[May 19, 2026 General Primary](2026-05-19-general-primary.md)",
                "Type": "general_primary",
                "Stage": "election",
                "Body": "ga-governor",
                "Seat": "sole",
                "Name (SOS)": "Governor",
            },
            heading="Governor",
            contests=[
                ContestData(
                    heading="Republican Primary",
                    candidates=[
                        {
                            "Candidate": "Brian Kemp",
                            "Status": "Qualified",
                            "Incumbent": "Yes",
                            "Occupation": "Governor",
                            "Qualified Date": "03/07/2026",
                        }
                    ],
                )
            ],
        )

        def mock_resolver(body_id: str, county_refs: dict) -> str | None:
            if body_id == "ga-governor":
                return "state"
            return None

        records = parse_result_to_records(result, mock_resolver)
        assert len(records) >= 1

    def test_multi_contest_to_multiple_records(self) -> None:
        """Multi-contest ParseResult produces one ElectionJSONL per contest section."""
        result = ParseResult(
            file_path=Path("2026-05-19-bibb.md"),
            file_type=FileType.MULTI_CONTEST,
            metadata={
                "ID": "770e8400-e29b-41d4-a716-446655440002",
                "Format Version": "1",
                "Election": "[May 19, 2026](../overview.md)",
                "Type": "general_primary",
            },
            heading="Bibb County \u2014 Local Elections",
            contests=[
                ContestData(
                    heading="Board of Education At Large-Post 7",
                    body_id="bibb-boe",
                    seat_id="post-7",
                    candidates=[{"Candidate": "John Smith", "Status": "Qualified"}],
                ),
                ContestData(
                    heading="Sheriff",
                    body_id="bibb-sheriff",
                    seat_id="sole",
                    candidates=[{"Candidate": "Bob Jones", "Status": "Qualified"}],
                ),
            ],
        )

        def mock_resolver(body_id: str, county_refs: dict) -> str | None:
            return "county"

        records = parse_result_to_records(result, mock_resolver)
        # Should produce at least the contest-level records
        assert len(records) >= 1

    def test_invalid_record_produces_error(self) -> None:
        """Invalid record (missing required fields) produces an error, not an exception."""
        result = ParseResult(
            file_path=Path("bad.md"),
            file_type=FileType.OVERVIEW,
            metadata={
                "ID": "550e8400-e29b-41d4-a716-446655440000",
                # Missing Name (SOS), Date, Type - should fail validation
            },
            heading="Bad File",
        )

        def mock_resolver(body_id: str, county_refs: dict) -> str | None:
            return None

        records = parse_result_to_records(result, mock_resolver)
        # Should have errors rather than crash
        assert len(records) == 1
        assert len(records[0].errors) > 0


class TestWriteJSONL:
    """Tests for writing validated records to JSONL files."""

    def test_writes_valid_records(self, tmp_path: Path) -> None:
        """Valid records are written to JSONL output file."""
        records = [
            {
                "schema_version": 1,
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_date": "2026-05-19",
                "event_name": "May 19, 2026 General Primary",
                "event_type": "general_primary",
            }
        ]
        output = tmp_path / "election_events.jsonl"
        written, errors = write_jsonl(records, output, ElectionEventJSONL)

        assert written == 1
        assert errors == []
        assert output.exists()

        lines = output.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_type"] == "general_primary"

    def test_skips_invalid_records(self, tmp_path: Path) -> None:
        """Invalid records are skipped and reported as errors."""
        records = [
            {
                "schema_version": 1,
                # Missing required fields
            }
        ]
        output = tmp_path / "election_events.jsonl"
        written, errors = write_jsonl(records, output, ElectionEventJSONL)

        assert written == 0
        assert len(errors) > 0

    def test_mixed_valid_invalid(self, tmp_path: Path) -> None:
        """Mix of valid and invalid records: valid are written, invalid logged."""
        records = [
            {
                "schema_version": 1,
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "event_date": "2026-05-19",
                "event_name": "Valid Record",
                "event_type": "general_primary",
            },
            {
                "schema_version": 1,
                # Invalid - missing required fields
            },
        ]
        output = tmp_path / "election_events.jsonl"
        written, errors = write_jsonl(records, output, ElectionEventJSONL)

        assert written == 1
        assert len(errors) == 1
