"""File-level normalization engine for election and candidate markdown files.

Walks directories, detects file types, applies all normalization rules,
and builds NormalizationReport results. Supports dry-run mode for
reporting changes without writing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from voter_api.lib.normalizer.report import NormalizationReport
from voter_api.lib.normalizer.rules import normalize_date, normalize_occupation, normalize_url
from voter_api.lib.normalizer.title_case import smart_title_case
from voter_api.lib.normalizer.types import FileChange, FileNormalizationResult

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------

_ELECTION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_ELECTION_TYPE_SLUGS: frozenset[str] = frozenset(
    {
        "general-primary",
        "general",
        "special",
        "special-primary",
        "municipal",
        "runoff",
        "special-runoff",
    }
)


def _detect_file_type(file_path: Path) -> str:
    """Detect the markdown file type.

    Args:
        file_path: Path to the markdown file.

    Returns:
        One of: 'overview', 'single', 'multi', 'candidate', 'unknown'.
    """
    name = file_path.name

    # Candidate files live in a candidates/ directory
    if "candidates" in file_path.parts:
        return "candidate"

    # Files in a counties/ subdirectory are multi-contest files
    if file_path.parent.name == "counties":
        return "multi"

    # Check for election date prefix (YYYY-MM-DD-...)
    if _ELECTION_DATE_RE.match(name):
        slug_match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", name)
        if slug_match:
            slug = slug_match.group(1)
            if slug in _ELECTION_TYPE_SLUGS:
                return "overview"
            return "single"

    return "unknown"


# ---------------------------------------------------------------------------
# Metadata table parsing helpers
# ---------------------------------------------------------------------------

_META_ROW_RE = re.compile(r"^\|([^|]+)\|([^|]*)\|$")


def _replace_metadata_value(content: str, field_name: str, new_value: str) -> str:
    """Replace a value in a markdown metadata table row.

    Args:
        content: Markdown file content.
        field_name: The field name to update.
        new_value: The replacement value.

    Returns:
        Updated content string.
    """
    pattern = rf"(\|\s*{re.escape(field_name)}\s*\|)\s*.*?\s*(\|)"
    replacement = rf"\1 {new_value} \2"
    return re.sub(pattern, replacement, content)


# ---------------------------------------------------------------------------
# Field category sets
# ---------------------------------------------------------------------------

_NAME_FIELDS: frozenset[str] = frozenset({"Name", "Name (SOS)"})

_DATE_FIELDS: frozenset[str] = frozenset(
    {
        "Date",
        "Registration Deadline",
        "Early Voting Start",
        "Early Voting End",
        "Absentee Request Deadline",
        "Qualifying Period Start",
        "Qualifying Period End",
        "Election Day",
        "Qualified Date",
    }
)

_URL_FIELDS: frozenset[str] = frozenset({"Photo URL", "Website", "URL"})

# Fields that contain election type/stage values -- skip title case
_VOCABULARY_FIELDS: frozenset[str] = frozenset(
    {
        "Type",
        "Stage",
        "ID",
        "Format Version",
        "Contests",
        "Candidates",
        "Party",
        "Filing Status",
        "Incumbent",
        "Is Incumbent",
        "Status",
        "Election ID",
        "Election",
        "Contest File",
        "Body",
        "Seat",
        "Email",
        "Source",
        "Ballotpedia",
        "Open States",
        "VPAP",
    }
)

# ALL-CAPS remnant detection: 4+ uppercase letters (not known acronyms)
_CAPS_REMNANT_RE = re.compile(r"\b([A-Z]{4,})\b")
_KNOWN_ACRONYMS: frozenset[str] = frozenset(
    {
        "UUID",
        "YYYY",
        "HTML",
        "HTTP",
        "HTTPS",
        "JSON",
        "JSONL",
        "REST",
        "API",
        "URL",
        "CORS",
        "CSRF",
        "NATO",
        "NASA",
        "FEMA",
        "EEOC",
        "NAACP",
        "ACLU",
        "USDA",
        "FDIC",
        "FDOT",
        "GDOT",
        "SOS",
        "BOE",
        "BOC",
        "PSC",
        "PUD",
        "EMC",
        "CEO",
        "CFO",
        "COO",
        "CTO",
        "CPA",
        "LLC",
        "LLP",
        "CORP",
        "HVAC",
        "OCGA",
        "True",
        "False",
        "None",
    }
)


def _has_caps_remnants(text: str) -> list[str]:
    """Find ALL CAPS words (4+ chars) that aren't known acronyms.

    Args:
        text: The text to inspect.

    Returns:
        List of ALL CAPS words that are likely normalization remnants.
    """
    matches = _CAPS_REMNANT_RE.findall(text)
    return [m for m in matches if m not in _KNOWN_ACRONYMS]


# ---------------------------------------------------------------------------
# Candidate table normalization
# ---------------------------------------------------------------------------

_CANDIDATE_TABLE_HEADER_RE = re.compile(r"^\|\s*Candidate\s*\|.*\|$", re.IGNORECASE)


def _normalize_candidate_table_row(row: str, header_cols: list[str]) -> tuple[str, list[FileChange]]:
    """Normalize a single candidate table data row.

    Args:
        row: The pipe-separated table row string.
        header_cols: Column names from the header row.

    Returns:
        Tuple of (normalized_row, list_of_changes).
    """
    changes: list[FileChange] = []
    raw_parts = row.split("|")
    if len(raw_parts) < 3:
        return row, changes

    # Extract cells (skip first and last empty strings from split)
    cells = [p.strip() for p in raw_parts[1:-1]]

    new_cells = []
    for i, cell in enumerate(cells):
        col_name = header_cols[i] if i < len(header_cols) else ""
        new_cell = cell

        if col_name == "Candidate":
            # Handle linked candidates: [Name](path.md)
            link_match = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", cell)
            if link_match:
                name_text = link_match.group(1)
                link_path = link_match.group(2)
                new_name = smart_title_case(name_text)
                if new_name != name_text:
                    changes.append(
                        FileChange(
                            field_name="Candidate",
                            original=name_text,
                            normalized=new_name,
                            rule="smart_title_case",
                        )
                    )
                new_cell = f"[{new_name}]({link_path})"
            else:
                new_name = smart_title_case(cell)
                if new_name != cell:
                    changes.append(
                        FileChange(
                            field_name="Candidate",
                            original=cell,
                            normalized=new_name,
                            rule="smart_title_case",
                        )
                    )
                new_cell = new_name

        elif col_name == "Occupation":
            new_occ = normalize_occupation(cell)
            if new_occ != cell:
                changes.append(
                    FileChange(
                        field_name="Occupation",
                        original=cell,
                        normalized=new_occ,
                        rule="normalize_occupation",
                    )
                )
            new_cell = new_occ

        elif col_name == "Qualified Date":
            new_date = normalize_date(cell, target_format="slash")
            if new_date != cell:
                changes.append(
                    FileChange(
                        field_name="Qualified Date",
                        original=cell,
                        normalized=new_date,
                        rule="normalize_date",
                    )
                )
            new_cell = new_date

        new_cells.append(new_cell)

    return "| " + " | ".join(new_cells) + " |", changes


def _parse_table_header_cols(header_row: str) -> list[str]:
    """Parse column names from a markdown table header row.

    Args:
        header_row: The pipe-separated header row string.

    Returns:
        List of column name strings.
    """
    parts = header_row.split("|")
    return [p.strip() for p in parts[1:-1]]


# ---------------------------------------------------------------------------
# Calendar table normalization (ISO dates)
# ---------------------------------------------------------------------------

_CALENDAR_HEADER_RE = re.compile(r"^\|\s*Field\s*\|\s*Date\s*\|", re.IGNORECASE)


def _normalize_calendar_table_row(row: str) -> tuple[str, list[FileChange]]:
    """Normalize a calendar table row (dates in ISO format).

    Args:
        row: The pipe-separated table row string.

    Returns:
        Tuple of (normalized_row, list_of_changes).
    """
    changes: list[FileChange] = []
    raw_parts = row.split("|")
    if len(raw_parts) < 4:
        return row, changes

    cells = [p.strip() for p in raw_parts[1:-1]]
    if len(cells) < 2:
        return row, changes

    # Calendar table: | Field | Date | Source |
    # Column 1 (index 1) is the date value
    date_cell = cells[1]
    new_date = normalize_date(date_cell, target_format="iso")
    if new_date != date_cell:
        changes.append(
            FileChange(
                field_name="Calendar Date",
                original=date_cell,
                normalized=new_date,
                rule="normalize_date",
            )
        )
        cells[1] = new_date

    return "| " + " | ".join(cells) + " |", changes


# ---------------------------------------------------------------------------
# Metadata table normalization
# ---------------------------------------------------------------------------


def _determine_rule(field_name: str) -> str:
    """Determine the rule name for a given field.

    Args:
        field_name: The metadata field name.

    Returns:
        Human-readable rule name string.
    """
    if field_name in _NAME_FIELDS:
        return "smart_title_case"
    if field_name in _DATE_FIELDS:
        return "normalize_date"
    if field_name in _URL_FIELDS:
        return "normalize_url"
    if field_name == "Occupation":
        return "normalize_occupation"
    return "unknown"


def _normalize_metadata_row(row: str) -> tuple[str, list[FileChange]]:
    """Normalize a single metadata table row.

    Applies appropriate normalization based on the field name.

    Args:
        row: The pipe-separated table row string.

    Returns:
        Tuple of (normalized_row, list_of_changes).
    """
    changes: list[FileChange] = []
    match = _META_ROW_RE.match(row)
    if not match:
        return row, changes

    field_name = match.group(1).strip()
    value = match.group(2).strip()

    # Skip header/separator rows
    if field_name in ("Field", "---") or value in ("Value", "---"):
        return row, changes

    new_value = value

    if field_name in _NAME_FIELDS:
        new_value = smart_title_case(value)
    elif field_name in _DATE_FIELDS:
        new_value = normalize_date(value, target_format="slash")
    elif field_name in _URL_FIELDS:
        new_value = normalize_url(value)
    elif field_name == "Occupation":
        new_value = normalize_occupation(value)
    # Vocabulary fields are left as-is

    if new_value != value:
        changes.append(
            FileChange(
                field_name=field_name,
                original=value,
                normalized=new_value,
                rule=_determine_rule(field_name),
            )
        )
        return f"| {field_name} | {new_value} |", changes

    return row, changes


# ---------------------------------------------------------------------------
# Warnings detection helper
# ---------------------------------------------------------------------------


def _collect_caps_warnings(lines: list[str]) -> list[str]:
    """Scan lines for ALL CAPS remnants and return warning messages.

    Only checks lines that contain a pipe (table rows), not headings.

    Args:
        lines: List of content lines.

    Returns:
        List of warning strings.
    """
    warnings: list[str] = []
    for line_no, line in enumerate(lines, 1):
        remnants = _has_caps_remnants(line)
        if remnants and not line.strip().startswith("#") and "|" in line:
            for remnant in remnants:
                warnings.append(f"Line {line_no}: ALL CAPS remnant '{remnant}' not normalized")
    return warnings


# ---------------------------------------------------------------------------
# Content-level normalization by file type
# ---------------------------------------------------------------------------


def _normalize_election_content(
    content: str,
) -> tuple[str, list[FileChange], list[str]]:
    """Apply normalization rules to election (overview/single/multi) content.

    Args:
        content: File content string.

    Returns:
        Tuple of (normalized_content, all_changes, warnings).
    """
    lines = content.split("\n")
    new_lines: list[str] = []
    all_changes: list[FileChange] = []

    in_metadata_table = False
    in_calendar_table = False
    in_candidate_table = False
    candidate_header_cols: list[str] = []
    past_header_separator = False

    for raw_line in lines:
        line = raw_line

        # ── Section detection ────────────────────────────────────────────
        if line.startswith("## Metadata"):
            in_metadata_table = True
            in_calendar_table = False
            in_candidate_table = False
            candidate_header_cols = []
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("## Calendar"):
            in_metadata_table = False
            in_calendar_table = True
            in_candidate_table = False
            candidate_header_cols = []
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("## ") or line.startswith("### "):
            in_metadata_table = False
            in_calendar_table = False
            in_candidate_table = False
            candidate_header_cols = []
            past_header_separator = False
            new_lines.append(line)
            continue

        # ── Table row handling ───────────────────────────────────────────
        if line.startswith("|"):
            # Detect candidate table header
            if _CANDIDATE_TABLE_HEADER_RE.match(line):
                in_metadata_table = False
                in_calendar_table = False
                in_candidate_table = True
                candidate_header_cols = _parse_table_header_cols(line)
                past_header_separator = False
                new_lines.append(line)
                continue

            # Skip separator rows (|----|-----|)
            if re.match(r"^\|[-| ]+\|$", line):
                if in_candidate_table:
                    past_header_separator = True
                new_lines.append(line)
                continue

            # Calendar table rows
            if in_calendar_table:
                if _CALENDAR_HEADER_RE.match(line):
                    new_lines.append(line)
                    continue
                new_line, changes = _normalize_calendar_table_row(line)
                all_changes.extend(changes)
                new_lines.append(new_line)
                continue

            # Metadata table rows
            if in_metadata_table:
                new_line, changes = _normalize_metadata_row(line)
                all_changes.extend(changes)
                new_lines.append(new_line)
                continue

            # Candidate table data rows
            if in_candidate_table and past_header_separator:
                new_line, changes = _normalize_candidate_table_row(line, candidate_header_cols)
                all_changes.extend(changes)
                new_lines.append(new_line)
                continue

        new_lines.append(line)

    warnings = _collect_caps_warnings(new_lines)
    return "\n".join(new_lines), all_changes, warnings


# ---------------------------------------------------------------------------
# Candidate file-specific normalization
# ---------------------------------------------------------------------------


def _normalize_candidate_file_content(
    content: str,
) -> tuple[str, list[FileChange], list[str]]:
    """Normalize a global candidate markdown file.

    Applies title case to the H1 name, Name metadata field, and candidate
    name links. Normalizes URLs in Links table and Photo URL. Normalizes
    dates in election sections.

    Args:
        content: File content string.

    Returns:
        Tuple of (normalized_content, all_changes, warnings).
    """
    lines = content.split("\n")
    new_lines: list[str] = []
    all_changes: list[FileChange] = []

    in_metadata_table = False
    in_elections_section = False
    in_links_table = False
    past_header_separator = False

    for raw_line in lines:
        line = raw_line

        # H1 heading: the candidate's full name
        if line.startswith("# ") and not line.startswith("## "):
            name = line[2:].strip()
            new_name = smart_title_case(name)
            if new_name != name:
                all_changes.append(
                    FileChange(
                        field_name="H1 Name",
                        original=name,
                        normalized=new_name,
                        rule="smart_title_case",
                    )
                )
            new_lines.append(f"# {new_name}")
            continue

        # Section detection
        if line.startswith("## Metadata"):
            in_metadata_table = True
            in_elections_section = False
            in_links_table = False
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("## Links"):
            in_metadata_table = False
            in_links_table = True
            in_elections_section = False
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("## Elections"):
            in_metadata_table = False
            in_links_table = False
            in_elections_section = True
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("## "):
            in_metadata_table = False
            in_links_table = False
            in_elections_section = False
            past_header_separator = False
            new_lines.append(line)
            continue

        if line.startswith("|"):
            # Separator rows
            if re.match(r"^\|[-| ]+\|$", line):
                past_header_separator = True
                new_lines.append(line)
                continue

            # Detect Links table header
            if re.match(r"^\|\s*Type\s*\|\s*URL\s*\|", line, re.IGNORECASE):
                in_links_table = True
                past_header_separator = False
                new_lines.append(line)
                continue

            # Metadata table rows
            if in_metadata_table:
                match = _META_ROW_RE.match(line)
                if match:
                    field_name = match.group(1).strip()
                    value = match.group(2).strip()

                    if field_name in ("Field", "---") or value in ("Value", "---"):
                        new_lines.append(line)
                        continue

                    new_value = value
                    if field_name == "Name":
                        new_value = smart_title_case(value)
                    elif field_name == "Photo URL":
                        new_value = normalize_url(value)
                    elif field_name == "Qualified Date":
                        new_value = normalize_date(value, target_format="slash")

                    if new_value != value:
                        all_changes.append(
                            FileChange(
                                field_name=field_name,
                                original=value,
                                normalized=new_value,
                                rule=_determine_rule(field_name),
                            )
                        )
                        new_lines.append(f"| {field_name} | {new_value} |")
                        continue

                new_lines.append(line)
                continue

            # Links table data rows: normalize URL column
            if in_links_table and past_header_separator:
                parts = line.split("|")
                if len(parts) >= 4:
                    cells = [p.strip() for p in parts[1:-1]]
                    if len(cells) >= 2:
                        url_cell = cells[1]
                        new_url = normalize_url(url_cell)
                        if new_url != url_cell:
                            all_changes.append(
                                FileChange(
                                    field_name="URL",
                                    original=url_cell,
                                    normalized=new_url,
                                    rule="normalize_url",
                                )
                            )
                            cells[1] = new_url
                            new_lines.append("| " + " | ".join(cells) + " |")
                            continue

            # Elections section: normalize per-election metadata tables
            if in_elections_section:
                match = _META_ROW_RE.match(line)
                if match:
                    field_name = match.group(1).strip()
                    value = match.group(2).strip()
                    new_value = value
                    if field_name == "Qualified Date":
                        new_value = normalize_date(value, target_format="slash")
                    elif field_name == "Occupation":
                        new_value = normalize_occupation(value)

                    if new_value != value:
                        all_changes.append(
                            FileChange(
                                field_name=field_name,
                                original=value,
                                normalized=new_value,
                                rule=_determine_rule(field_name),
                            )
                        )
                        new_lines.append(f"| {field_name} | {new_value} |")
                        continue

        new_lines.append(line)

    warnings = _collect_caps_warnings(new_lines)
    return "\n".join(new_lines), all_changes, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_file(
    file_path: Path,
    *,
    dry_run: bool = False,
) -> FileNormalizationResult:
    """Normalize a single markdown file.

    Reads the file, detects its type, applies all normalization rules
    (title case on name fields, date formatting, URL normalization,
    occupation title case), flags ALL CAPS remnants as warnings, and
    writes the normalized content back unless dry_run is True.

    Args:
        file_path: Path to the markdown file to normalize.
        dry_run: If True, compute changes but do not write to disk.

    Returns:
        FileNormalizationResult with changes, warnings, and errors.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return FileNormalizationResult(
            file_path=file_path,
            errors=[f"Could not read file: {exc}"],
        )

    file_type = _detect_file_type(file_path)

    if file_type == "candidate":
        normalized_content, changes, warnings = _normalize_candidate_file_content(content)
    else:
        # overview, single, multi, unknown -- all use election content normalizer
        normalized_content, changes, warnings = _normalize_election_content(content)

    result = FileNormalizationResult(
        file_path=file_path,
        changes=changes,
        warnings=warnings,
    )

    if not dry_run and normalized_content != content:
        try:
            file_path.write_text(normalized_content, encoding="utf-8")
        except OSError as exc:
            result.errors.append(f"Could not write file: {exc}")

    return result


def normalize_directory(
    directory: Path,
    *,
    dry_run: bool = False,
    report_path: Path | None = None,
    file_type: str | None = None,
) -> NormalizationReport:
    """Normalize all markdown files in a directory.

    Walks the directory recursively, skips README.md files, applies
    normalize_file to each .md file, and builds an aggregate
    NormalizationReport. If report_path is provided, writes a JSON
    report to that path.

    Args:
        directory: Path to the directory to normalize.
        dry_run: If True, compute changes but do not write to disk.
        report_path: Optional path to write a JSON report.
        file_type: Optional file type filter ('candidate' to process
            only candidate files). If None, all .md files are processed.

    Returns:
        NormalizationReport with aggregate results.
    """
    report = NormalizationReport()

    md_files = sorted(directory.rglob("*.md"))
    md_files = [f for f in md_files if f.name != "README.md"]

    # Filter by file_type if requested
    if file_type == "candidate":
        md_files = [f for f in md_files if _detect_file_type(f) == "candidate"]

    for file_path in md_files:
        result = normalize_file(file_path, dry_run=dry_run)

        if result.errors:
            report.add_failure(file_path, result.errors)
        else:
            report.add_success(file_path, len(result.changes))

        for warning in result.warnings:
            report.add_warning(file_path, warning)

    if report_path is not None:
        report.write_json(report_path)

    return report
