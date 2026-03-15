"""JSONL writer for converted election data.

Converts ParseResult objects to JSONL-ready dicts and writes
validated records to JSONL files. All validation uses Pydantic
model_validate against the JSONL schema models.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from voter_api.lib.converter.types import ConversionResult, FileType, ParseResult

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# Normalize election type strings from old markdown format to ElectionType enum values.
# Handles human-readable values from the format-migration tool that weren't normalized.
_ELECTION_TYPE_NORMALIZE: dict[str, str] = {
    "partisan primary": "general_primary",
    "general and primary": "general_primary",
    "general & primary": "general_primary",
    "nonpartisan primary": "general_primary",
    "nonpartisan general": "general",
    "general primary": "general_primary",
    "special election": "special",
    "special primary": "special_primary",
    "municipal election": "municipal",
}


def write_jsonl(
    records: list[dict[str, Any]],
    output_path: Path,
    model_class: type[BaseModel],
) -> tuple[int, list[str]]:
    """Validate and write records to a JSONL file.

    Each record is validated against the Pydantic model. Valid records
    are written one per line. Invalid records are skipped and their
    errors are collected.

    Args:
        records: List of dicts to validate and write.
        output_path: Path to the output JSONL file.
        model_class: Pydantic model class for validation.

    Returns:
        Tuple of (count_written, list_of_error_strings).
    """
    written = 0
    errors: list[str] = []

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for i, record in enumerate(records):
            try:
                validated = model_class.model_validate(record)
                line = validated.model_dump_json()
                f.write(line + "\n")
                written += 1
            except ValidationError as e:
                errors.append(f"Record {i}: {e}")

    return written, errors


def parse_result_to_records(
    result: ParseResult,
    resolver: Callable[[str, dict], str | None],
    county_refs: dict | None = None,
) -> list[ConversionResult]:
    """Convert a ParseResult to JSONL-ready record dicts.

    Maps parsed metadata fields to JSONL schema fields and resolves
    Body IDs to boundary_type using the resolver function.

    Args:
        result: Parsed markdown data.
        resolver: Function to resolve Body ID to boundary_type.
        county_refs: County reference data (passed to resolver).

    Returns:
        List of ConversionResult objects with records and/or errors.
    """
    if county_refs is None:
        county_refs = {}

    if result.file_type == FileType.OVERVIEW:
        return [_overview_to_records(result)]
    if result.file_type == FileType.SINGLE_CONTEST:
        return [_single_contest_to_records(result, resolver, county_refs)]
    if result.file_type == FileType.MULTI_CONTEST:
        return [_multi_contest_to_records(result, resolver, county_refs)]

    return [
        ConversionResult(
            file_path=result.file_path,
            errors=[f"Unknown file type: {result.file_type}"],
        )
    ]


def _normalize_election_type(value: str) -> str:
    """Normalize a raw election type string to an ElectionType enum value.

    Handles human-readable type strings from old markdown format (e.g.,
    "Partisan Primary" -> "general_primary") and passes through already-
    normalized values unchanged.

    Args:
        value: Raw election type string from markdown metadata.

    Returns:
        Normalized ElectionType string value.
    """
    if not value:
        return value
    normalized = _ELECTION_TYPE_NORMALIZE.get(value.strip().lower())
    return normalized if normalized is not None else value


def _normalize_date(value: str) -> str | None:
    """Normalize a date string to ISO format (YYYY-MM-DD) or return None.

    Handles:
    - ISO format (YYYY-MM-DD) -> returned as-is
    - MM/DD/YYYY format -> converted to YYYY-MM-DD
    - Em-dash (—) or empty string -> None (treat as absent)

    Args:
        value: Raw date string from markdown metadata.

    Returns:
        ISO date string or None if value is absent/placeholder.
    """
    if not value or value in ("\u2014", "-", "--"):
        return None
    # Handle MM/DD/YYYY
    mm_dd_yyyy = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", value.strip())
    if mm_dd_yyyy:
        return f"{mm_dd_yyyy.group(3)}-{mm_dd_yyyy.group(1)}-{mm_dd_yyyy.group(2)}"
    return value


def _overview_to_records(result: ParseResult) -> ConversionResult:
    """Convert an overview ParseResult to an ElectionEventJSONL record."""
    from voter_api.schemas.jsonl.election_event import ElectionEventJSONL

    errors: list[str] = []
    records: list[dict[str, Any]] = []

    meta = result.metadata

    try:
        # Normalize event_date from metadata Date field (may be MM/DD/YYYY) or
        # fall back to filename-based date
        raw_date = meta.get("Date", "")
        event_date = _normalize_date(raw_date) or _extract_date_from_filename(result)

        record: dict[str, Any] = {
            "schema_version": 1,
            "id": meta.get("ID", ""),
            "event_date": event_date,
            "event_name": result.heading or meta.get("Name (SOS)", ""),
            "event_type": meta.get("Type", ""),
        }

        # Add calendar fields if present; skip em-dash placeholder values
        cal = result.calendar
        field_map = {
            "Registration Deadline": "registration_deadline",
            "Early Voting Start": "early_voting_start",
            "Early Voting End": "early_voting_end",
            "Absentee Request Deadline": "absentee_request_deadline",
            "Qualifying Period Start": "qualifying_start",
            "Qualifying Period End": "qualifying_end",
        }
        for md_field, jsonl_field in field_map.items():
            if md_field in cal:
                normalized = _normalize_date(cal[md_field])
                if normalized is not None:
                    record[jsonl_field] = normalized

        # Validate against Pydantic model
        ElectionEventJSONL.model_validate(record)
        records.append(record)
    except ValidationError as e:
        errors.append(f"ElectionEvent validation failed: {e}")
    except Exception as e:
        errors.append(f"Failed to build ElectionEvent record: {e}")

    return ConversionResult(
        file_path=result.file_path,
        records=records,
        errors=errors,
    )


def _single_contest_to_records(
    result: ParseResult,
    resolver: Callable[[str, dict], str | None],
    county_refs: dict,
) -> ConversionResult:
    """Convert a single-contest ParseResult to ElectionJSONL records."""
    errors: list[str] = []
    records: list[dict[str, Any]] = []

    meta = result.metadata
    body_id = meta.get("Body", "")
    seat_id = meta.get("Seat", "")

    # Resolve boundary_type from Body ID
    boundary_type = resolver(body_id, county_refs) if body_id else None

    try:
        record: dict[str, Any] = {
            "schema_version": 1,
            "id": meta.get("ID", ""),
            "election_event_id": _extract_election_event_id(meta),
            "name": result.heading or "",
            "name_sos": meta.get("Name (SOS)"),
            "election_date": _infer_election_date(meta, result),
            "election_type": _normalize_election_type(meta.get("Type", "")),
            "election_stage": meta.get("Stage", "election"),
            "boundary_type": boundary_type,
            "district_identifier": seat_id if seat_id else None,
        }
        records.append(record)
    except Exception as e:
        errors.append(f"Failed to build Election record: {e}")

    return ConversionResult(
        file_path=result.file_path,
        records=records,
        errors=errors,
    )


def _multi_contest_to_records(
    result: ParseResult,
    resolver: Callable[[str, dict], str | None],
    county_refs: dict,
) -> ConversionResult:
    """Convert a multi-contest ParseResult to multiple ElectionJSONL records."""
    errors: list[str] = []
    records: list[dict[str, Any]] = []

    meta = result.metadata
    election_date = _infer_election_date(meta, result)

    for contest in result.contests:
        try:
            boundary_type = resolver(contest.body_id, county_refs) if contest.body_id else None

            record: dict[str, Any] = {
                "schema_version": 1,
                "id": meta.get("ID", ""),  # File-level ID for now
                "election_event_id": _extract_election_event_id(meta),
                "name": contest.heading,
                "election_date": election_date,
                "election_type": _normalize_election_type(meta.get("Type", "")),
                "election_stage": meta.get("Stage", "election"),
                "boundary_type": boundary_type,
                "district_identifier": contest.seat_id,
            }
            records.append(record)
        except Exception as e:
            errors.append(f"Failed to build record for '{contest.heading}': {e}")

    return ConversionResult(
        file_path=result.file_path,
        records=records,
        errors=errors,
    )


def _extract_date_from_filename(result: ParseResult) -> str:
    """Extract YYYY-MM-DD date from filename prefix.

    Args:
        result: ParseResult with file_path.

    Returns:
        ISO date string from filename, or empty string if not matched.
    """
    name = result.file_path.stem
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    if date_match:
        return date_match.group(1)
    return ""


def _extract_election_event_id(metadata: dict[str, str]) -> str | None:
    """Extract the election event UUID from an Election metadata link.

    The Election field contains a markdown link like:
    [May 19, 2026 General Primary](2026-05-19-general-primary.md)

    For now, returns a placeholder since the event ID is resolved
    during import, not during conversion.
    """
    # The election_event_id can't be fully resolved at conversion time
    # since we'd need to read the referenced overview file.
    # Return None -- it will be resolved during import.
    return None


def _infer_election_date(metadata: dict[str, str], result: ParseResult) -> str:
    """Infer the election date from metadata or file path.

    Checks metadata Date field first (normalizing MM/DD/YYYY to ISO),
    then falls back to the YYYY-MM-DD prefix in the filename.

    Args:
        metadata: Parsed metadata dict.
        result: ParseResult with file_path for fallback.

    Returns:
        ISO date string (YYYY-MM-DD) or empty string if not found.
    """
    if "Date" in metadata:
        normalized = _normalize_date(metadata["Date"])
        if normalized:
            return normalized

    return _extract_date_from_filename(result)
