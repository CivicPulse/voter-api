"""Markdown-to-JSONL converter library.

Public API for converting election markdown files to validated JSONL
records. The converter is deterministic (no AI), validates against
Pydantic JSONL schemas, and resolves Body/Seat references to
boundary_type using county reference files.

No database dependency -- reads markdown files and writes JSONL files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voter_api.lib.converter.parser import parse_markdown
from voter_api.lib.converter.report import ConversionReport
from voter_api.lib.converter.resolver import (
    load_county_references,
    resolve_body,
)
from voter_api.lib.converter.types import ConversionResult, FileType
from voter_api.lib.converter.writer import parse_result_to_records, write_jsonl

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "convert_directory",
    "convert_file",
]


def convert_directory(
    directory: Path,
    output: Path | None = None,
    fail_fast: bool = False,
    counties_dir: Path | None = None,
) -> ConversionReport:
    """Convert an entire election directory from markdown to JSONL.

    Walks the directory tree, identifies file types by path pattern,
    parses each file, validates records, and writes JSONL output.

    Args:
        directory: Path to the election directory to convert.
        output: Output directory for JSONL files. Defaults to
            sibling 'jsonl/' directory next to the input directory.
        fail_fast: If True, stop on first failure. Default False.
        counties_dir: Path to county reference files directory.
            Defaults to data/states/GA/counties/ relative to project root.

    Returns:
        ConversionReport with aggregate results.
    """
    report = ConversionReport()

    if not directory.exists():
        return report

    # Determine output directory
    if output is None:
        output = directory.parent / "jsonl"
    output.mkdir(parents=True, exist_ok=True)

    # Load county references for resolver
    if counties_dir is None:
        counties_dir = _find_counties_dir(directory)
    county_refs = load_county_references(counties_dir) if counties_dir else {}

    # Find all markdown files
    md_files = sorted(directory.rglob("*.md"))

    for md_file in md_files:
        result = convert_file(
            md_file,
            output=output,
            county_refs=county_refs,
        )

        if result.errors:
            report.add_failure(md_file, result.errors)
            if fail_fast:
                break
        else:
            report.add_success(md_file, len(result.records))

    # Write JSON report
    report.write_json(output / "conversion-report.json")

    return report


def convert_file(
    file_path: Path,
    output: Path | None = None,
    county_refs: dict | None = None,
) -> ConversionResult:
    """Convert a single markdown file to JSONL records.

    Args:
        file_path: Path to the markdown file to convert.
        output: Output directory for JSONL files. If None, records
            are returned without writing to disk.
        county_refs: Pre-loaded county references. If None, will
            attempt to load from default location.

    Returns:
        ConversionResult with records and/or errors.
    """
    if county_refs is None:
        counties_dir = _find_counties_dir(file_path)
        county_refs = load_county_references(counties_dir) if counties_dir else {}

    # Parse the markdown file
    parse_result = parse_markdown(file_path)

    # Check for parse errors
    if parse_result.errors:
        return ConversionResult(
            file_path=file_path,
            errors=parse_result.errors,
        )

    # Convert to JSONL records
    conversion_results = parse_result_to_records(parse_result, resolve_body, county_refs)

    # Aggregate all records and errors
    all_records: list[dict] = []
    all_errors: list[str] = []
    for cr in conversion_results:
        all_records.extend(cr.records)
        all_errors.extend(cr.errors)

    # Write to disk if output specified
    if output and all_records and not all_errors:
        _write_records_to_disk(parse_result.file_type, all_records, output)

    return ConversionResult(
        file_path=file_path,
        records=all_records,
        errors=all_errors,
    )


def _write_records_to_disk(file_type: FileType, records: list[dict], output_dir: Path) -> None:
    """Write records to appropriate JSONL files based on file type."""
    from voter_api.schemas.jsonl.election import ElectionJSONL
    from voter_api.schemas.jsonl.election_event import ElectionEventJSONL

    if file_type == FileType.OVERVIEW:
        write_jsonl(records, output_dir / "election_events.jsonl", ElectionEventJSONL)
    else:
        write_jsonl(records, output_dir / "elections.jsonl", ElectionJSONL)


def _find_counties_dir(start_path: Path) -> Path | None:
    """Find the county reference files directory relative to a path.

    Walks up the directory tree looking for data/states/GA/counties/.
    """
    current = start_path if start_path.is_dir() else start_path.parent

    for _ in range(10):  # Limit search depth
        candidate = current / "data" / "states" / "GA" / "counties"
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None
