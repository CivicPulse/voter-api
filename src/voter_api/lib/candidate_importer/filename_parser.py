"""Parse GA Secretary of State Qualified Candidates CSV filenames to extract metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_MONTH_NUMBERS: dict[str, int] = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12,
}

_ELECTION_TYPE_MAP: dict[str, str] = {
    "SPECIAL_ELECTION": "special",
    "GENERAL_AND_PRIMARY_ELECTION": "general_primary",
    "PRIMARY_ELECTION": "primary",
    "GENERAL_ELECTION": "general",
    "RUNOFF_ELECTION": "runoff",
}

_FILENAME_RE = re.compile(r"^([A-Z]+)_(\d{1,2})_(\d{4})-(.+)_Qualified_Candidates\.csv$")


@dataclass(frozen=True)
class CandidateFileInfo:
    """Metadata extracted from a Qualified Candidates CSV filename.

    Attributes:
        election_date: The date of the election derived from the filename.
        election_type: Normalized election type (e.g. "general", "primary").
        original_filename: The original filename (basename only).
    """

    election_date: date
    election_type: str
    original_filename: str


def parse_candidate_filename(filename: str) -> CandidateFileInfo:
    """Parse a GA SoS Qualified Candidates CSV filename into structured metadata.

    Accepts full paths or bare filenames. Extracts the election date and type
    from the filename convention used by the GA Secretary of State.

    Args:
        filename: The filename or full path to parse. Only the basename is used.

    Returns:
        A CandidateFileInfo with the extracted election date, type, and
        original filename.

    Raises:
        ValueError: If the filename does not match the expected pattern, contains
            an unrecognized month name, an invalid date, or an unknown election type.
    """
    basename = Path(filename).name
    match = _FILENAME_RE.match(basename)
    if not match:
        raise ValueError(f"Filename does not match expected pattern: {basename}")

    month_name, day_str, year_str, election_type_raw = match.groups()

    month = _MONTH_NUMBERS.get(month_name)
    if month is None:
        raise ValueError(f"Unrecognized month name: {month_name}")

    try:
        election_date = date(int(year_str), month, int(day_str))
    except ValueError as exc:
        raise ValueError(f"Invalid date in filename: {month_name} {day_str}, {year_str}") from exc

    election_type = _ELECTION_TYPE_MAP.get(election_type_raw)
    if election_type is None:
        raise ValueError(f"Unknown election type: {election_type_raw}")

    return CandidateFileInfo(
        election_date=election_date,
        election_type=election_type,
        original_filename=basename,
    )
