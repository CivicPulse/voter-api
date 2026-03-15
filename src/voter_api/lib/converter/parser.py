"""Markdown parser for election data files.

Parses election overview, single-contest, and multi-contest markdown
files using mistune's AST renderer. Extracts metadata tables, candidate
tables, contest sections, and calendar data. Deterministic -- no AI,
no UUID generation.
"""

from __future__ import annotations

import re
import uuid as uuid_mod
from typing import TYPE_CHECKING

import mistune

from voter_api.lib.converter.types import ContestData, FileType, ParseResult

if TYPE_CHECKING:
    from pathlib import Path


def parse_markdown(file_path: Path) -> ParseResult:
    """Parse an election markdown file and extract structured data.

    Args:
        file_path: Path to the markdown file to parse.

    Returns:
        ParseResult with extracted metadata, contests, and any errors.
    """
    text = file_path.read_text(encoding="utf-8")
    md = mistune.create_markdown(renderer=None, plugins=["table"])
    tokens = md(text)
    assert isinstance(tokens, list)

    heading = _extract_h1_heading(tokens)
    metadata = _extract_metadata_table(tokens)
    calendar = _extract_calendar_table(tokens)
    errors: list[str] = []
    warnings: list[str] = []

    # Validate UUID
    _validate_uuid(metadata, file_path, errors)

    # Detect file type
    file_type = _detect_file_type(file_path, metadata, tokens)

    # Extract contests based on file type
    contests: list[ContestData] = []
    if file_type == FileType.MULTI_CONTEST:
        contests = _extract_contests(tokens)
    elif file_type == FileType.SINGLE_CONTEST:
        contests = _extract_single_contest_data(tokens)

    return ParseResult(
        file_path=file_path,
        file_type=file_type,
        metadata=metadata,
        contests=contests,
        errors=errors,
        warnings=warnings,
        calendar=calendar,
        heading=heading,
    )


def _extract_h1_heading(tokens: list[dict]) -> str:
    """Extract the H1 heading text from tokens."""
    for token in tokens:
        if token.get("type") == "heading" and token.get("attrs", {}).get("level") == 1:
            return _extract_text_from_children(token.get("children", []))
    return ""


def _extract_text_from_children(children: list[dict]) -> str:
    """Recursively extract plain text from token children."""
    parts: list[str] = []
    for child in children:
        if child.get("type") in ("text", "codespan"):
            parts.append(child.get("raw", child.get("text", "")))
        elif child.get("type") in ("softbreak", "linebreak", "hardbreak"):
            # Render line breaks as newline to separate tokens on adjacent lines
            parts.append("\n")
        elif "children" in child:
            parts.append(_extract_text_from_children(child["children"]))
    return "".join(parts)


def _extract_metadata_table(tokens: list[dict]) -> dict[str, str]:
    """Extract the first Field/Value metadata table from tokens.

    Looks for a table immediately following an H2 heading containing
    'Metadata'. The table must have Field and Value columns.
    """
    metadata: dict[str, str] = {}
    in_metadata_section = False

    for token in tokens:
        if token.get("type") == "heading":
            level = token.get("attrs", {}).get("level", 0)
            text = _extract_text_from_children(token.get("children", []))
            if level == 2 and "Metadata" in text:
                in_metadata_section = True
                continue
            if level == 2 and in_metadata_section:
                break  # End of metadata section

        if in_metadata_section and token.get("type") == "table":
            rows = _parse_table_rows(token)
            for row in rows:
                if len(row) >= 2:
                    field_name = row[0].strip()
                    value = row[1].strip()
                    if field_name and field_name.lower() != "field":
                        metadata[field_name] = value
            break  # Only first table in metadata section

    return metadata


def _extract_calendar_table(tokens: list[dict]) -> dict[str, str]:
    """Extract calendar dates from a Calendar section table.

    Calendar tables have three columns: Field, Date, Source.
    Only the Field and Date columns are extracted.
    """
    calendar: dict[str, str] = {}
    in_calendar_section = False

    for token in tokens:
        if token.get("type") == "heading":
            level = token.get("attrs", {}).get("level", 0)
            text = _extract_text_from_children(token.get("children", []))
            if level == 2 and "Calendar" in text:
                in_calendar_section = True
                continue
            if level == 2 and in_calendar_section:
                break

        if in_calendar_section and token.get("type") == "table":
            rows = _parse_table_rows(token)
            for row in rows:
                if len(row) >= 2:
                    field_name = row[0].strip()
                    date_val = row[1].strip()
                    if field_name and field_name.lower() != "field":
                        calendar[field_name] = date_val
            break

    return calendar


def _parse_table_rows(table_token: dict) -> list[list[str]]:
    """Parse a table token into a list of row lists.

    Each row is a list of cell text values. The header row is excluded.
    """
    rows: list[list[str]] = []

    # Table has children: table_head and table_body
    children = table_token.get("children", [])

    for child in children:
        if child.get("type") == "table_body":
            body_children = child.get("children", [])
            for row_token in body_children:
                if row_token.get("type") == "table_row":
                    cells = []
                    for cell_token in row_token.get("children", []):
                        if cell_token.get("type") == "table_cell":
                            cell_text = _extract_text_from_children(cell_token.get("children", []))
                            cells.append(cell_text)
                    rows.append(cells)

    return rows


def _parse_candidate_table(table_token: dict) -> list[dict[str, str]]:
    """Parse a candidate table token into a list of candidate dicts.

    Handles both 5-column (new format) and 7-column (legacy format) tables.
    """
    candidates: list[dict[str, str]] = []

    # Get header columns
    headers: list[str] = []
    children = table_token.get("children", [])
    for child in children:
        if child.get("type") == "table_head":
            # mistune AST: table_head -> table_cell (direct, no table_row wrapper)
            for cell_token in child.get("children", []):
                if cell_token.get("type") == "table_cell":
                    header_text = _extract_text_from_children(cell_token.get("children", []))
                    headers.append(header_text.strip())

    # Skip if this doesn't look like a candidate table
    if not headers or headers[0].lower() not in ("candidate", "name"):
        return []

    # Get body rows
    rows = _parse_table_rows(table_token)
    for row in rows:
        candidate: dict[str, str] = {}
        for i, value in enumerate(row):
            if i < len(headers):
                candidate[headers[i]] = value.strip()
        if candidate:
            candidates.append(candidate)

    return candidates


def _validate_uuid(metadata: dict[str, str], file_path: Path, errors: list[str]) -> None:
    """Validate the ID field in metadata.

    Adds errors for missing, empty, or invalid UUIDs.
    The converter MUST NOT generate UUIDs per uuid-strategy.md.
    """
    id_value = metadata.get("ID", "").strip()

    if not id_value:
        errors.append(f"UUID_MISSING: {file_path} - No ID found in metadata table. Run backfill to assign UUIDs.")
        return

    try:
        uuid_mod.UUID(id_value)
    except ValueError:
        errors.append(f'UUID_INVALID: {file_path} - Invalid UUID value: "{id_value}"')


def _detect_file_type(file_path: Path, metadata: dict[str, str], tokens: list[dict]) -> FileType:
    """Determine the file type from metadata and structure.

    - Overview: Has Date field, no Body/Seat, no Contests field
    - Multi-contest: Has Contests field in metadata, or is in counties/ dir
    - Single-contest: Has Body and Seat fields
    """
    # Check for multi-contest indicators
    if "Contests" in metadata:
        return FileType.MULTI_CONTEST

    # Check for county subdirectory pattern
    if "counties" in file_path.parts:
        return FileType.MULTI_CONTEST

    # Check for single-contest indicators (Body/Seat)
    if "Body" in metadata or "Seat" in metadata:
        return FileType.SINGLE_CONTEST

    # Check for Election link (contest files have this, overviews don't)
    if "Election" in metadata:
        return FileType.SINGLE_CONTEST

    # Default to overview (has Date, no Body/Seat)
    return FileType.OVERVIEW


def _extract_contests(tokens: list[dict]) -> list[ContestData]:
    """Extract individual contest sections from multi-contest files.

    Splits by ### headings within the ## Contests section.
    Extracts Body/Seat from metadata lines and candidate tables.
    """
    contests: list[ContestData] = []
    in_contests_section = False
    current_contest: ContestData | None = None

    for token in tokens:
        if token.get("type") == "heading":
            level = token.get("attrs", {}).get("level", 0)
            text = _extract_text_from_children(token.get("children", []))

            if level == 2 and "Contests" in text:
                in_contests_section = True
                continue
            if level == 2 and in_contests_section:
                # End of Contests section -- append last contest and stop.
                # Do NOT fall through to the post-loop append below.
                if current_contest:
                    contests.append(current_contest)
                    current_contest = None  # Prevent double-append after break
                break
            if level == 3 and in_contests_section:
                # New contest heading
                if current_contest:
                    contests.append(current_contest)
                current_contest = ContestData(heading=text)
                continue

        if in_contests_section and current_contest:
            # Look for Body/Seat metadata line in paragraph
            if token.get("type") == "paragraph":
                para_text = _extract_text_from_children(token.get("children", []))
                body_match = re.search(r"\*\*Body:\*\*\s*(\S+)", para_text)
                seat_match = re.search(r"\*\*Seat:\*\*\s*(\S+)", para_text)

                # Also try without the bold markers (plain text after AST)
                if not body_match:
                    body_match = re.search(r"Body:\s*(\S+)", para_text)
                if not seat_match:
                    seat_match = re.search(r"Seat:\s*(\S+)", para_text)

                if body_match:
                    current_contest.body_id = body_match.group(1)
                if seat_match:
                    current_contest.seat_id = seat_match.group(1)

            # Look for candidate table
            elif token.get("type") == "table":
                candidates = _parse_candidate_table(token)
                if candidates:
                    current_contest.candidates.extend(candidates)

    # Don't forget the last contest
    if current_contest:
        contests.append(current_contest)

    return contests


def _extract_single_contest_data(tokens: list[dict]) -> list[ContestData]:
    """Extract candidate data from single-contest files.

    Handles both partisan primary format (multiple party sections)
    and non-partisan format (single Candidates section).
    """
    contests: list[ContestData] = []
    current_contest: ContestData | None = None

    for token in tokens:
        if token.get("type") == "heading":
            level = token.get("attrs", {}).get("level", 0)
            text = _extract_text_from_children(token.get("children", []))

            if level == 2:
                # Party section (e.g., "Republican Primary") or "Candidates"
                if current_contest:
                    contests.append(current_contest)

                current_contest = ContestData(heading=text)
                continue

        if current_contest and token.get("type") == "table":
            candidates = _parse_candidate_table(token)
            if candidates:
                current_contest.candidates.extend(candidates)

    if current_contest:
        contests.append(current_contest)

    # Filter out non-candidate sections (like Metadata, Data Source)
    return [
        c for c in contests if c.candidates and c.heading.lower() not in ("metadata", "data source", "data sources")
    ]
