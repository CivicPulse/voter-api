"""Shared JSONL file reader with Pydantic validation.

Reads JSONL files line-by-line, validates each line against a Pydantic
model, and returns separate lists of valid records and errors.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ValidationError


def read_jsonl(
    path: Path,
    model_class: type[BaseModel],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read a JSONL file and validate each line against a Pydantic model.

    Args:
        path: Path to the JSONL file.
        model_class: Pydantic model class to validate each line against.

    Returns:
        Tuple of (valid_records, errors).
        valid_records: List of validated record dicts (serialized from model).
        errors: List of dicts with 'line', 'raw', and 'error' keys.
    """
    valid_records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with path.open() as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(
                    {
                        "line": line_num,
                        "raw": line[:200],
                        "error": f"Invalid JSON: {e}",
                    }
                )
                continue

            try:
                validated = model_class.model_validate(raw)
                valid_records.append(validated.model_dump(mode="python"))
            except ValidationError as e:
                errors.append(
                    {
                        "line": line_num,
                        "raw": line[:200],
                        "error": str(e),
                    }
                )
                logger.warning(f"JSONL validation error on line {line_num}: {e}")

    logger.info(f"Read {path.name}: {len(valid_records)} valid, {len(errors)} errors")
    return valid_records, errors
