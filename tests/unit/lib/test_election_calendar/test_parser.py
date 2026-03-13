"""Tests for the election calendar JSONL parser."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from voter_api.lib.election_calendar.parser import CalendarEntry, parse_calendar_jsonl


class TestParseCalendarJsonl:
    """Tests for parse_calendar_jsonl."""

    def test_parse_full_entry(self, tmp_path: Path) -> None:
        """All fields present are parsed correctly."""
        record = {
            "election_name": "General Primary Election",
            "election_date": "2026-05-19",
            "registration_deadline": "2026-04-20",
            "early_voting_start": "2026-04-27",
            "early_voting_end": "2026-05-15",
            "absentee_request_deadline": "2026-04-10",
            "qualifying_start": "2026-03-02T00:00:00",
            "qualifying_end": "2026-03-06T23:59:59",
        }
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text(json.dumps(record) + "\n")

        entries = parse_calendar_jsonl(jsonl_file)

        assert len(entries) == 1
        e = entries[0]
        assert e.election_name == "General Primary Election"
        assert e.election_date == date(2026, 5, 19)
        assert e.registration_deadline == date(2026, 4, 20)
        assert e.early_voting_start == date(2026, 4, 27)
        assert e.early_voting_end == date(2026, 5, 15)
        assert e.absentee_request_deadline == date(2026, 4, 10)
        assert e.qualifying_start == datetime(2026, 3, 2, 0, 0, 0)  # noqa: DTZ001
        assert e.qualifying_end == datetime(2026, 3, 6, 23, 59, 59)  # noqa: DTZ001

    def test_parse_minimal_entry(self, tmp_path: Path) -> None:
        """Only required fields present; optionals default to None."""
        record = {
            "election_name": "Special Election",
            "election_date": "2026-11-03",
        }
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text(json.dumps(record) + "\n")

        entries = parse_calendar_jsonl(jsonl_file)

        assert len(entries) == 1
        e = entries[0]
        assert e.election_name == "Special Election"
        assert e.election_date == date(2026, 11, 3)
        assert e.registration_deadline is None
        assert e.early_voting_start is None
        assert e.early_voting_end is None
        assert e.absentee_request_deadline is None
        assert e.qualifying_start is None
        assert e.qualifying_end is None

    def test_parse_multiple_entries(self, tmp_path: Path) -> None:
        """Multiple JSONL lines produce multiple entries."""
        records = [
            {"election_name": "Primary", "election_date": "2026-05-19"},
            {"election_name": "General", "election_date": "2026-11-03"},
            {"election_name": "Runoff", "election_date": "2026-12-01"},
        ]
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        entries = parse_calendar_jsonl(jsonl_file)

        assert len(entries) == 3
        assert entries[0].election_name == "Primary"
        assert entries[1].election_name == "General"
        assert entries[2].election_name == "Runoff"

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        """Empty file returns empty list."""
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("")

        entries = parse_calendar_jsonl(jsonl_file)

        assert entries == []

    def test_parse_blank_lines_skipped(self, tmp_path: Path) -> None:
        """Blank lines between records are skipped."""
        record = {"election_name": "Test", "election_date": "2026-01-01"}
        content = "\n\n" + json.dumps(record) + "\n\n"
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text(content)

        entries = parse_calendar_jsonl(jsonl_file)

        assert len(entries) == 1

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        """Missing election_name raises KeyError."""
        record = {"election_date": "2026-05-19"}
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text(json.dumps(record) + "\n")

        with pytest.raises(KeyError, match="election_name"):
            parse_calendar_jsonl(jsonl_file)

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        """Invalid JSON line raises JSONDecodeError."""
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text("not valid json\n")

        with pytest.raises(json.JSONDecodeError):
            parse_calendar_jsonl(jsonl_file)

    def test_date_parsing_iso_format(self, tmp_path: Path) -> None:
        """ISO 8601 dates are parsed correctly."""
        record = {
            "election_name": "Test",
            "election_date": "2026-12-31",
            "registration_deadline": "2026-12-01",
        }
        jsonl_file = tmp_path / "calendar.jsonl"
        jsonl_file.write_text(json.dumps(record) + "\n")

        entries = parse_calendar_jsonl(jsonl_file)

        assert entries[0].election_date == date(2026, 12, 31)
        assert entries[0].registration_deadline == date(2026, 12, 1)


class TestCalendarEntryDataclass:
    """Tests for CalendarEntry defaults."""

    def test_defaults(self) -> None:
        """Optional fields default to None."""
        entry = CalendarEntry(
            election_name="Test",
            election_date=date(2026, 1, 1),
        )
        assert entry.registration_deadline is None
        assert entry.early_voting_start is None
        assert entry.early_voting_end is None
        assert entry.absentee_request_deadline is None
        assert entry.qualifying_start is None
        assert entry.qualifying_end is None
