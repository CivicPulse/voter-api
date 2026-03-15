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


def _overview_to_records(result: ParseResult) -> ConversionResult:
    """Convert an overview ParseResult to an ElectionEventJSONL record."""
    from voter_api.schemas.jsonl.election_event import ElectionEventJSONL

    errors: list[str] = []
    records: list[dict[str, Any]] = []

    meta = result.metadata

    try:
        record: dict[str, Any] = {
            "schema_version": 1,
            "id": meta.get("ID", ""),
            "event_date": meta.get("Date", ""),
            "event_name": result.heading or meta.get("Name (SOS)", ""),
            "event_type": meta.get("Type", ""),
        }

        # Add calendar fields if present
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
                record[jsonl_field] = cal[md_field]

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
            "election_type": meta.get("Type", ""),
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
                "election_type": meta.get("Type", ""),
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


def _extract_election_event_id(metadata: dict[str, str]) -> str:
    """Extract the election event UUID from an Election metadata link.

    The Election field contains a markdown link like:
    [May 19, 2026 General Primary](2026-05-19-general-primary.md)

    For now, returns a placeholder since the event ID is resolved
    during import, not during conversion.
    """
    # The election_event_id can't be fully resolved at conversion time
    # since we'd need to read the referenced overview file.
    # Return a placeholder that will be resolved during import.
    return "00000000-0000-0000-0000-000000000000"


def _infer_election_date(metadata: dict[str, str], result: ParseResult) -> str:
    """Infer the election date from metadata or file path.

    Checks metadata Date field first, then tries to extract from filename.
    """
    if "Date" in metadata:
        return metadata["Date"]

    # Try to extract from filename pattern: YYYY-MM-DD-*
    name = result.file_path.stem
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    if date_match:
        return date_match.group(1)

    return ""
