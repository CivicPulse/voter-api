"""Election calendar parsing and preprocessing library.

Provides tools for extracting election calendar data from GA SoS source
files (XLSX, PDF, HTML) and parsing standardized JSONL templates.
"""

from voter_api.lib.election_calendar.parser import CalendarEntry, parse_calendar_jsonl

__all__ = [
    "CalendarEntry",
    "parse_calendar_jsonl",
]
