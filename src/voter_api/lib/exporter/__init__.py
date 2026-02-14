"""Exporter library — public API for voter data export.

Provides format-specific writers and a unified export function.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voter_api.lib.exporter.csv_writer import DEFAULT_COLUMNS, write_csv
from voter_api.lib.exporter.geojson_writer import write_geojson
from voter_api.lib.exporter.json_writer import write_json

# Format registry mapping format names to writer functions
_WRITERS: dict[str, Callable[..., int]] = {
    "csv": write_csv,
    "json": write_json,
    "geojson": write_geojson,
}

SUPPORTED_FORMATS = list(_WRITERS.keys())


@dataclass
class ExportResult:
    """Result of an export operation."""

    record_count: int
    output_path: Path
    file_size_bytes: int


def export_voters(
    records: Iterable[dict[str, Any]],
    output_format: str,
    output_path: Path,
    *,
    columns: list[str] | None = None,
) -> ExportResult:
    """Export voter records to the specified format.

    Args:
        records: Iterable of voter record dicts.
        output_format: Output format (csv, json, geojson).
        output_path: Path to write the output file.
        columns: Column selection for CSV format.

    Returns:
        ExportResult with record count and file info.

    Raises:
        ValueError: If the format is not supported.
    """
    if output_format not in _WRITERS:
        msg = f"Unsupported format: {output_format}. Supported: {SUPPORTED_FORMATS}"
        raise ValueError(msg)

    writer = _WRITERS[output_format]

    if output_format == "csv" and columns:
        count = write_csv(output_path, records, columns=columns)
    else:
        count = writer(output_path, records)

    file_size = output_path.stat().st_size

    return ExportResult(
        record_count=count,
        output_path=output_path,
        file_size_bytes=file_size,
    )


__all__ = [
    "DEFAULT_COLUMNS",
    "ExportResult",
    "SUPPORTED_FORMATS",
    "export_voters",
    "write_csv",
    "write_geojson",
    "write_json",
]
