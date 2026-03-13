"""JSONL template parser for preprocessed candidate import files.

Reads the JSONL output from the preprocessor and yields validated
batches of candidate records for database import.
"""

import contextlib
import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from loguru import logger

from voter_api.lib.candidate_importer.validator import validate_candidate_record

_REQUIRED_FIELDS = ("election_name", "election_date", "candidate_name")


def parse_candidate_import_jsonl(
    file_path: Path,
    batch_size: int = 500,
) -> Iterator[list[dict]]:
    """Parse a preprocessed candidate JSONL file and yield record batches.

    Reads the JSONL file line by line, validates required fields and date
    formats, and yields batches of record dicts. Records with validation
    errors have a ``_parse_error`` key set with the error details.

    Args:
        file_path: Path to the preprocessed JSONL file.
        batch_size: Number of records per yielded batch.

    Yields:
        Lists of record dicts, each list containing up to ``batch_size``
        records.
    """
    batch: list[dict] = []
    line_num = 0

    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line_num += 1
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                record = {"_parse_error": f"Line {line_num}: Invalid JSON: {e}"}
                batch.append(record)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
                continue

            if not isinstance(record, dict):
                record = {"_parse_error": f"Line {line_num}: Expected JSON object, got {type(record).__name__}"}
                batch.append(record)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
                continue

            # Validate required fields
            errors = validate_candidate_record(record)
            if errors:
                record["_parse_error"] = f"Line {line_num}: {'; '.join(errors)}"

            # Parse election_date from ISO string to date object
            election_date_str = record.get("election_date")
            if isinstance(election_date_str, str):
                with contextlib.suppress(ValueError):
                    record["election_date"] = date.fromisoformat(election_date_str)

            # Parse qualified_date if present
            qualified_date_str = record.get("qualified_date")
            if isinstance(qualified_date_str, str) and qualified_date_str:
                try:
                    record["qualified_date"] = date.fromisoformat(qualified_date_str)
                except ValueError:
                    logger.warning(f"Line {line_num}: Invalid qualified_date: {qualified_date_str}")
                    record["_parse_error"] = f"Invalid qualified_date: {record.get('qualified_date')}"

            batch.append(record)
            if len(batch) >= batch_size:
                yield batch
                batch = []

    if batch:
        yield batch
