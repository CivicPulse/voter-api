"""Parser for standardized election calendar JSONL templates.

Reads line-delimited JSON files where each line represents a single
election calendar entry with dates in ISO 8601 format.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass
class CalendarEntry:
    """A single election calendar entry from the standardized template.

    Attributes:
        election_name: Display name of the election.
        election_date: Date the election takes place.
        registration_deadline: Last day to register for this election.
        early_voting_start: First day of advance/early voting.
        early_voting_end: Last day of advance/early voting.
        absentee_request_deadline: Last day to request an absentee ballot.
        qualifying_start: Start of the candidate qualifying period.
        qualifying_end: End of the candidate qualifying period.
    """

    election_name: str
    election_date: date
    registration_deadline: date | None = None
    early_voting_start: date | None = None
    early_voting_end: date | None = None
    absentee_request_deadline: date | None = None
    qualifying_start: datetime | None = None
    qualifying_end: datetime | None = None


def _parse_date(value: str | None) -> date | None:
    """Parse an ISO 8601 date string, returning None for missing values.

    Args:
        value: Date string in YYYY-MM-DD format, or None.

    Returns:
        Parsed date or None.
    """
    if value is None:
        return None
    return date.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 datetime string, returning None for missing values.

    Args:
        value: Datetime string in ISO 8601 format, or None.

    Returns:
        Parsed datetime or None.
    """
    if value is None:
        return None
    return datetime.fromisoformat(value)


def parse_calendar_jsonl(file_path: Path) -> list[CalendarEntry]:
    """Parse a calendar JSONL template file into CalendarEntry objects.

    Each line of the file must be a JSON object with at least
    ``election_name`` and ``election_date`` fields. Optional date fields
    are parsed when present.

    Args:
        file_path: Path to the JSONL file.

    Returns:
        List of parsed CalendarEntry objects.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If a line contains invalid JSON.
        KeyError: If required fields are missing.
    """
    entries: list[CalendarEntry] = []
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return entries

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        entry = CalendarEntry(
            election_name=record["election_name"],
            election_date=date.fromisoformat(record["election_date"]),
            registration_deadline=_parse_date(record.get("registration_deadline")),
            early_voting_start=_parse_date(record.get("early_voting_start")),
            early_voting_end=_parse_date(record.get("early_voting_end")),
            absentee_request_deadline=_parse_date(record.get("absentee_request_deadline")),
            qualifying_start=_parse_datetime(record.get("qualifying_start")),
            qualifying_end=_parse_datetime(record.get("qualifying_end")),
        )
        entries.append(entry)

    return entries
