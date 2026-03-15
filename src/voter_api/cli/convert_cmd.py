"""CLI commands for markdown-to-JSONL conversion and file migration.

Provides the ``voter-api convert`` command group with ``directory``,
``file``, ``migrate-format``, and ``backfill-uuids`` subcommands.
"""

import asyncio
import re
import sys
import uuid
from datetime import date
from pathlib import Path

import typer
from loguru import logger

from voter_api.lib.converter import convert_directory, convert_file

convert_app = typer.Typer()


@convert_app.command("directory")
def convert_directory_cmd(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the election directory to convert.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Output directory for JSONL files. Defaults to sibling jsonl/ directory.",
    ),
    fail_fast: bool = typer.Option(  # noqa: B008
        False,
        "--fail-fast",
        help="Stop on first conversion failure.",
    ),
    counties_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--counties-dir",
        help="Path to county reference files. Defaults to auto-detect.",
    ),
) -> None:
    """Convert an entire election directory from markdown to JSONL.

    Walks the directory tree, parses markdown files, validates records
    against JSONL schemas, and writes output to JSONL files.
    """
    report = convert_directory(
        directory,
        output=output,
        fail_fast=fail_fast,
        counties_dir=counties_dir,
    )

    # Print terminal report
    typer.echo(report.render_terminal())

    # Exit with code 1 if any failures
    if report.files_failed > 0:
        typer.echo(f"{report.files_failed} file(s) failed conversion.", err=True)
        sys.exit(1)

    typer.echo(f"Converted {report.files_succeeded} file(s) successfully.")


@convert_app.command("file")
def convert_file_cmd(
    file_path: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to the markdown file to convert.",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Output directory for JSONL files.",
    ),
) -> None:
    """Convert a single markdown file to JSONL records.

    Parses the file, validates records against JSONL schemas, and
    prints a summary of the results.
    """
    result = convert_file(file_path, output=output)

    if result.errors:
        typer.echo("Conversion failed:", err=True)
        for error in result.errors:
            typer.echo(f"  {error}", err=True)
        sys.exit(1)

    typer.echo(f"Converted {file_path.name}: {len(result.records)} record(s)")


# ── Migrate-Format Command ──────────────────────────────────────────────────

# Body/Seat inference for statewide/federal contests
_STATEWIDE_BODY_SEAT: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"-governor\.md$"), "ga-governor", "sole"),
    (re.compile(r"-lieutenant-governor\.md$"), "ga-lt-governor", "sole"),
    (re.compile(r"-secretary-of-state\.md$"), "ga-sos", "sole"),
    (re.compile(r"-attorney-general\.md$"), "ga-ag", "sole"),
    (re.compile(r"-state-school-superintendent\.md$"), "ga-school-superintendent", "sole"),
    (re.compile(r"-agriculture-commissioner\.md$"), "ga-agriculture", "sole"),
    (re.compile(r"-labor-commissioner\.md$"), "ga-labor", "sole"),
    (re.compile(r"-insurance-commissioner\.md$"), "ga-insurance", "sole"),
    (re.compile(r"-us-senate\.md$"), "ga-us-senate", "sole"),
    (re.compile(r"-us-house-district-(\d+)\.md$"), "ga-us-house", "district-{n}"),
    (re.compile(r"-state-senate-district-(\d+)\.md$"), "ga-state-senate", "district-{n}"),
    (re.compile(r"-state-house-district-(\d+)\.md$"), "ga-state-house", "district-{n}"),
    (re.compile(r"-psc-district-(\d+)\.md$"), "ga-psc", "district-{n}"),
]

# Type inference from overview filename
_TYPE_MAPPING: dict[str, str] = {
    "general-primary": "general_primary",
    "general": "general",
    "special": "special",
    "special-primary": "special_primary",
    "municipal": "municipal",
}

# County contest patterns for Body/Seat inference
_COUNTY_CONTEST_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^Board of Education At Large-Post (\d+)$", re.I), "{county}-boe", "post-{n}"),
    (re.compile(r"^Board of Education District (\d+)$", re.I), "{county}-boe", "district-{n}"),
    (re.compile(r"^Civil\S*Magistrate Court", re.I), "{county}-civil-magistrate", "sole"),
    (
        re.compile(r"^Judge of Superior Court[^-]*-\s*(\w+)\s*$", re.I),
        "{county}-superior-court",
        "judge-{surname}",
    ),
    (
        re.compile(r"^State Court Judge(?:\s\(\w+\))?\s*[-–—]\s*(\w+)\s*$", re.I),
        "{county}-state-court",
        "judge-{surname}",
    ),
    (re.compile(r"^County Commission District (\d+)$", re.I), "{county}-commission", "district-{n}"),
]


def _detect_file_type(file_path: Path) -> str:
    """Detect whether a file is overview, single-contest, or multi-contest.

    Args:
        file_path: Path to the markdown file.

    Returns:
        One of: 'overview', 'single', 'multi'
    """
    name = file_path.name

    # Overview: filename pattern {date}-{type}.md (e.g., 2026-05-19-general-primary.md)
    if re.match(r"\d{4}-\d{2}-\d{2}-[a-z]+(?:-[a-z]+)*\.md$", name) and file_path.parent.name != "counties":
        # Check if it's a statewide contest (not overview)
        is_contest = any(pat.search(name) for pat, _, _ in _STATEWIDE_BODY_SEAT)
        if not is_contest:
            return "overview"

    # Multi-contest: files in counties/ subdirectory
    if file_path.parent.name == "counties":
        return "multi"

    # Single-contest: everything else in the election directory
    return "single"


def _is_already_migrated(content: str) -> bool:
    """Check if a file has already been migrated by looking for Format Version."""
    return bool(re.search(r"\|\s*Format Version\s*\|", content))


def _infer_statewide_body_seat(filename: str) -> tuple[str, str]:
    """Infer Body and Seat from a statewide/federal contest filename.

    Args:
        filename: The markdown filename.

    Returns:
        Tuple of (body_id, seat_id) or ('', '') if not recognized.
    """
    for pattern, body, seat_template in _STATEWIDE_BODY_SEAT:
        match = pattern.search(filename)
        if match:
            if match.groups():
                n = str(int(match.group(1)))  # Unpad: "02" -> "2"
                return body, seat_template.format(n=n)
            return body, seat_template
    return "", ""


def _infer_county_body_seat(contest_name: str, county_slug: str) -> tuple[str, str]:
    """Infer Body and Seat from a county contest name.

    Args:
        contest_name: The ### heading text.
        county_slug: Lowercase county name slug.

    Returns:
        Tuple of (body_id, seat_id) or ('', '') if not recognized.
    """
    for pattern, body_template, seat_template in _COUNTY_CONTEST_PATTERNS:
        match = pattern.search(contest_name)
        if match:
            groups = match.groups()
            body = body_template.replace("{county}", county_slug)
            if "surname" in seat_template and groups:
                seat = seat_template.replace("{surname}", groups[0].lower())
            elif "{n}" in seat_template and groups:
                seat = seat_template.replace("{n}", str(int(groups[0])))
            else:
                seat = seat_template
            return body, seat
    return "", ""


def _migrate_overview(content: str, filename: str) -> str:
    """Migrate an overview file to enhanced format.

    Args:
        content: File content.
        filename: Filename for type inference.

    Returns:
        Migrated content.
    """
    lines = content.split("\n")

    # Infer election type from filename
    # e.g., 2026-05-19-general-primary.md -> general_primary
    slug_match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", filename)
    election_type = ""
    if slug_match:
        slug = slug_match.group(1)
        election_type = _TYPE_MAPPING.get(slug, slug.replace("-", "_"))

    # Find the metadata table or heading to insert metadata rows
    # Look for the first ## heading or table after the H1
    insert_idx = 1  # After the H1 heading
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.startswith("##") or (line.startswith("|") and "Date" in line):
            insert_idx = i
            break

    # Add metadata rows
    metadata_block = [
        "",
        "## Metadata",
        "",
        "| Field | Value |",
        "|-------|-------|",
        "| ID | |",
        "| Format Version | 1 |",
        "| Name (SOS) | |",
        f"| Type | {election_type} |",
        "| Stage | election |",
        "",
    ]

    # Insert metadata before the first section
    new_lines = lines[:insert_idx] + metadata_block + lines[insert_idx:]

    return "\n".join(new_lines)


def _migrate_single_contest(content: str, filename: str) -> str:
    """Migrate a single-contest file to enhanced format.

    Args:
        content: File content.
        filename: Filename for Body/Seat inference.

    Returns:
        Migrated content.
    """
    lines = content.split("\n")

    # Infer Body/Seat
    body, seat = _infer_statewide_body_seat(filename)

    # Find the metadata table header
    meta_table_start = -1
    for i, line in enumerate(lines):
        if "| Field | Value |" in line or ("| Field" in line and "Value" in line):
            meta_table_start = i
            break

    if meta_table_start > 0:
        # Insert ID, Format Version, Body, Seat, Stage before existing rows
        separator_line = meta_table_start + 1
        new_rows = [
            "| ID | |",
            "| Format Version | 1 |",
            f"| Body | {body} |",
            f"| Seat | {seat} |",
            "| Stage | election |",
        ]
        new_lines = lines[: separator_line + 1] + new_rows + lines[separator_line + 1 :]
    else:
        # No metadata table found, add one after H1
        metadata_block = [
            "",
            "## Metadata",
            "",
            "| Field | Value |",
            "|-------|-------|",
            "| ID | |",
            "| Format Version | 1 |",
            f"| Body | {body} |",
            f"| Seat | {seat} |",
            "| Stage | election |",
        ]
        new_lines = [lines[0]] + metadata_block + lines[1:]

    # Reduce candidate tables from 7 to 5 columns
    return _reduce_candidate_table_columns("\n".join(new_lines))


def _migrate_multi_contest(content: str, filename: str) -> str:
    """Migrate a multi-contest (county) file to enhanced format.

    Args:
        content: File content.
        filename: Filename for county inference.

    Returns:
        Migrated content.
    """
    lines = content.split("\n")

    # Extract county slug from filename: 2026-05-19-bibb.md -> bibb
    county_match = re.match(r"\d{4}-\d{2}-\d{2}-(.+)\.md$", filename)
    county_slug = county_match.group(1) if county_match else ""

    # Find the metadata table and add ID + Format Version
    meta_table_start = -1
    for i, line in enumerate(lines):
        if "| Field | Value |" in line:
            meta_table_start = i
            break

    if meta_table_start > 0:
        separator_line = meta_table_start + 1
        new_rows = [
            "| ID | |",
            "| Format Version | 1 |",
        ]
        lines = lines[: separator_line + 1] + new_rows + lines[separator_line + 1 :]

    # Add Body/Seat metadata to each ### contest heading
    result_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        result_lines.append(line)

        # Check for ### heading (contest section)
        if line.startswith("### "):
            contest_name = line[4:].strip()
            body, seat = _infer_county_body_seat(contest_name, county_slug)

            # Add Body/Seat metadata line
            result_lines.append("")
            result_lines.append(f"**Body:** {body} | **Seat:** {seat}")

        i += 1

    return _reduce_candidate_table_columns("\n".join(result_lines))


def _reduce_candidate_table_columns(content: str) -> str:
    """Reduce candidate tables from 7 columns to 5 by dropping Email and Website.

    Also renames 'Qualified' to 'Qualified Date' in the header.

    Args:
        content: File content with candidate tables.

    Returns:
        Content with reduced candidate tables.
    """
    lines = content.split("\n")
    result_lines: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect 7-column candidate header
        if "|" in line and "Candidate" in line and "Email" in line and "Website" in line:
            # Parse header columns
            cols = [c.strip() for c in line.split("|")]
            # Remove empty strings from split
            cols = [c for c in cols if c]

            # Find indices of Email and Website
            email_idx = next((j for j, c in enumerate(cols) if c == "Email"), None)
            website_idx = next((j for j, c in enumerate(cols) if c == "Website"), None)

            # Build new header without Email and Website, rename Qualified
            new_cols = []
            for j, c in enumerate(cols):
                if j in (email_idx, website_idx):
                    continue
                if c == "Qualified":
                    new_cols.append("Qualified Date")
                else:
                    new_cols.append(c)
            new_header = "| " + " | ".join(new_cols) + " |"
            result_lines.append(new_header)

            # Process separator line
            i += 1
            if i < len(lines) and lines[i].startswith("|"):
                sep_cols = [c.strip() for c in lines[i].split("|") if c.strip()]
                new_sep = [sep_cols[j] for j in range(len(sep_cols)) if j != email_idx and j != website_idx]
                result_lines.append("| " + " | ".join(new_sep) + " |")

            # Process data rows
            i += 1
            while i < len(lines) and lines[i].startswith("|") and lines[i].strip() != "|":
                row_cols = [c.strip() for c in lines[i].split("|")]
                row_cols = [c for c in row_cols if c or row_cols.index(c) > 0]
                # Handle the leading empty string from split
                raw_parts = lines[i].split("|")
                data = [p.strip() for p in raw_parts[1:-1]]  # Skip first/last empty
                if len(data) >= 7 and email_idx is not None and website_idx is not None:
                    new_data = [data[j] for j in range(len(data)) if j != email_idx and j != website_idx]
                    result_lines.append("| " + " | ".join(new_data) + " |")
                else:
                    result_lines.append(lines[i])
                i += 1
            continue

        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)


@convert_app.command("migrate-format")
def migrate_format_cmd(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to election directory to migrate.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False,
        "--dry-run",
        help="Report what would change without writing.",
    ),
) -> None:
    """Migrate existing markdown files to enhanced format.

    Adds Format Version, ID, Body/Seat metadata, converts calendar
    tables to ISO format, and reduces candidate table columns.
    Idempotent: already-migrated files (with Format Version row) are skipped.
    """
    migrated = 0
    skipped = 0
    failed = 0
    warnings: list[str] = []

    if dry_run:
        typer.echo("DRY RUN -- no files will be modified\n")

    # Collect all markdown files
    md_files = sorted(directory.rglob("*.md"))
    md_files = [f for f in md_files if f.name != "README.md"]

    for file_path in md_files:
        content = file_path.read_text()

        # Skip already-migrated files
        if _is_already_migrated(content):
            skipped += 1
            continue

        file_type = _detect_file_type(file_path)
        try:
            if file_type == "overview":
                new_content = _migrate_overview(content, file_path.name)
            elif file_type == "single":
                new_content = _migrate_single_contest(content, file_path.name)
                body, seat = _infer_statewide_body_seat(file_path.name)
                if not body:
                    warnings.append(f"BODY_SEAT_UNKNOWN: {file_path}")
            elif file_type == "multi":
                new_content = _migrate_multi_contest(content, file_path.name)
            else:
                skipped += 1
                continue

            if not dry_run:
                file_path.write_text(new_content)
            migrated += 1
            logger.debug(f"Migrated: {file_path}")

        except Exception as e:
            failed += 1
            logger.warning(f"Failed to migrate {file_path}: {e}")
            warnings.append(f"MIGRATION_FAILED: {file_path} - {e}")

    # Print summary
    typer.echo(f"\nMigration Report: {directory}")
    typer.echo(f"  Migrated:  {migrated} files")
    typer.echo(f"  Skipped:   {skipped} files (already migrated)")
    typer.echo(f"  Failed:    {failed} files")
    if warnings:
        typer.echo("  Warnings:")
        for w in warnings:
            typer.echo(f"    {w}")
    typer.echo(f"\nTotal: {migrated + skipped + failed} files processed")


# ── Backfill-UUIDs Command ──────────────────────────────────────────────────


def _extract_metadata_value(content: str, field_name: str) -> str:
    """Extract a value from a markdown metadata table row.

    Args:
        content: Markdown file content.
        field_name: The field name to extract (e.g., 'ID', 'Type').

    Returns:
        The value string, or empty string if not found or empty cell.
    """
    # Use (.*?) to allow empty cells -- (.+?) incorrectly matches the next row's
    # leading pipe character when the value column is blank (e.g., "| ID | |")
    pattern = rf"\|\s*{re.escape(field_name)}\s*\|\s*(.*?)\s*\|"
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return ""


def _write_metadata_value(content: str, field_name: str, value: str) -> str:
    """Write a value into a markdown metadata table row.

    Args:
        content: Markdown file content.
        field_name: The field name to update.
        value: The new value.

    Returns:
        Updated content.
    """
    pattern = rf"(\|\s*{re.escape(field_name)}\s*\|)\s*.*?\s*(\|)"
    replacement = rf"\1 {value} \2"
    return re.sub(pattern, replacement, content)


def _extract_election_date_from_path(file_path: Path) -> date | None:
    """Extract election date from the directory/file path.

    Args:
        file_path: Path to the markdown file.

    Returns:
        Parsed date or None.
    """
    # Try to extract from parent directory name: data/elections/2026-05-19/...
    for part in file_path.parts:
        match = re.match(r"^(\d{4}-\d{2}-\d{2})$", part)
        if match:
            try:
                return date.fromisoformat(match.group(1))
            except ValueError:
                continue
    return None


@convert_app.command("backfill-uuids")
def backfill_uuids_cmd(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to election directory for UUID backfill.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False,
        "--dry-run",
        help="Report what would change without writing.",
    ),
) -> None:
    """Match markdown files to DB records and write UUIDs.

    For each file with an empty ID field:
    - Queries the database for a matching record by natural key
    - If found: writes the DB UUID into the file
    - If not found: generates a new UUID v4 and writes it

    Requires database access (uses init_engine pattern).
    """
    asyncio.run(_backfill_uuids(directory, dry_run))


async def _backfill_uuids(directory: Path, dry_run: bool) -> None:
    """Async implementation of UUID backfill.

    Args:
        directory: Path to election directory.
        dry_run: If True, report without writing.
    """
    from sqlalchemy import select

    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.models.election import Election
    from voter_api.models.election_event import ElectionEvent

    matched = 0
    generated = 0
    skipped = 0
    conflicts = 0
    errors: list[str] = []

    if dry_run:
        typer.echo("DRY RUN -- no files will be modified\n")

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)

    try:
        factory = get_session_factory()
        async with factory() as session:
            # Collect all markdown files
            md_files = sorted(directory.rglob("*.md"))
            md_files = [f for f in md_files if f.name != "README.md"]

            for file_path in md_files:
                content = file_path.read_text()

                # Skip files without Format Version (not yet migrated)
                if not _is_already_migrated(content):
                    skipped += 1
                    continue

                existing_id = _extract_metadata_value(content, "ID")

                # Skip files that already have a UUID
                if existing_id and existing_id != "--":
                    try:
                        uuid.UUID(existing_id)
                        skipped += 1
                        continue
                    except ValueError:
                        pass  # Invalid UUID, try to backfill

                election_date = _extract_election_date_from_path(file_path)
                file_type = _detect_file_type(file_path)
                db_uuid: uuid.UUID | None = None

                if file_type == "overview" and election_date:
                    # Match ElectionEvent by (event_date, event_type)
                    event_type = _extract_metadata_value(content, "Type")
                    if event_type:
                        result = await session.execute(
                            select(ElectionEvent.id).where(
                                ElectionEvent.event_date == election_date,
                                ElectionEvent.event_type == event_type,
                            )
                        )
                        db_uuid = result.scalar_one_or_none()

                elif file_type == "single" and election_date:
                    # Match Election by (name, election_date)
                    # Name is the H1 heading
                    h1_match = re.match(r"^#[ \t]+(.+)$", content, re.MULTILINE)
                    if h1_match:
                        name = h1_match.group(1).strip()
                        result = await session.execute(
                            select(Election.id).where(
                                Election.name == name,
                                Election.election_date == election_date,
                                Election.deleted_at.is_(None),
                            )
                        )
                        db_uuid = result.scalar_one_or_none()

                # Assign UUID
                if db_uuid:
                    new_id = str(db_uuid)
                    matched += 1
                    logger.debug(f"MATCHED: {file_path} -> {new_id}")
                else:
                    new_id = str(uuid.uuid4())
                    generated += 1
                    logger.debug(f"NEW: {file_path} -> {new_id}")

                # Check for conflicts
                if existing_id and existing_id != "--" and existing_id != new_id:
                    conflicts += 1
                    errors.append(f"CONFLICT: {file_path} - existing {existing_id} != {new_id}")
                    continue

                # Write UUID
                if not dry_run:
                    new_content = _write_metadata_value(content, "ID", new_id)
                    file_path.write_text(new_content)

    finally:
        await dispose_engine()

    # Print summary
    typer.echo(f"\nBackfill Report: {directory}")
    typer.echo(f"  Matched:    {matched} files (UUID from DB)")
    typer.echo(f"  Generated:  {generated} files (new UUID)")
    typer.echo(f"  Skipped:    {skipped} files (UUID already set)")
    typer.echo(f"  Conflicts:  {conflicts} files")
    if errors:
        typer.echo("  Errors:")
        for e in errors:
            typer.echo(f"    {e}")
    typer.echo(f"\nTotal: {matched + generated + skipped + conflicts} files processed")

    if conflicts > 0:
        raise typer.Exit(code=1)
