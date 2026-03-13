"""Auto-detect dispatcher for election calendar preprocessing.

Determines the correct preprocessor based on file extension and supports
merging entries from multiple source files.
"""

import json
from pathlib import Path

from loguru import logger

from voter_api.lib.election_calendar.html_preprocessor import preprocess_html_calendar
from voter_api.lib.election_calendar.parser import CalendarEntry, parse_calendar_jsonl
from voter_api.lib.election_calendar.pdf_preprocessor import preprocess_pdf_calendar
from voter_api.lib.election_calendar.xlsx_preprocessor import preprocess_xlsx_calendar


def _detect_and_preprocess(input_path: Path, output_path: Path) -> int:
    """Dispatch to the correct preprocessor based on file extension.

    Args:
        input_path: Source file path.
        output_path: JSONL output path.

    Returns:
        Number of entries written.

    Raises:
        ValueError: If the file extension is not supported.
    """
    suffix = input_path.suffix.lower()
    if suffix == ".xlsx":
        return preprocess_xlsx_calendar(input_path, output_path)
    if suffix == ".pdf":
        return preprocess_pdf_calendar(input_path, output_path)
    if suffix in (".html", ".htm"):
        return preprocess_html_calendar(input_path, output_path)
    msg = f"Unsupported file format: {suffix}. Expected .xlsx, .pdf, .html, or .htm"
    raise ValueError(msg)


def _merge_entries(all_entries: list[list[CalendarEntry]]) -> list[CalendarEntry]:
    """Merge calendar entries from multiple sources.

    Entries are keyed by ``(election_name, election_date)``. Non-None
    values from later sources override earlier ones for matching keys.

    Args:
        all_entries: List of entry lists, one per source file (in order).

    Returns:
        Merged list of CalendarEntry objects.
    """
    merged: dict[tuple[str, str], CalendarEntry] = {}

    for entries in all_entries:
        for entry in entries:
            key = (entry.election_name, str(entry.election_date))
            if key in merged:
                existing = merged[key]
                # Non-None values from the later source override
                if entry.registration_deadline is not None:
                    existing.registration_deadline = entry.registration_deadline
                if entry.early_voting_start is not None:
                    existing.early_voting_start = entry.early_voting_start
                if entry.early_voting_end is not None:
                    existing.early_voting_end = entry.early_voting_end
                if entry.absentee_request_deadline is not None:
                    existing.absentee_request_deadline = entry.absentee_request_deadline
                if entry.qualifying_start is not None:
                    existing.qualifying_start = entry.qualifying_start
                if entry.qualifying_end is not None:
                    existing.qualifying_end = entry.qualifying_end
            else:
                merged[key] = CalendarEntry(
                    election_name=entry.election_name,
                    election_date=entry.election_date,
                    registration_deadline=entry.registration_deadline,
                    early_voting_start=entry.early_voting_start,
                    early_voting_end=entry.early_voting_end,
                    absentee_request_deadline=entry.absentee_request_deadline,
                    qualifying_start=entry.qualifying_start,
                    qualifying_end=entry.qualifying_end,
                )

    return list(merged.values())


def preprocess_calendar(
    input_path: Path,
    output_path: Path,
    merge_paths: list[Path] | None = None,
) -> int:
    """Auto-detect source format and preprocess calendar data.

    If ``merge_paths`` is provided, processes all files and merges entries
    (later files' values override earlier ones for matching elections).

    Args:
        input_path: Primary source calendar file.
        output_path: Path for the final JSONL output.
        merge_paths: Additional source files to merge with the primary.

    Returns:
        Total number of calendar entries written.

    Raises:
        ValueError: If any file has an unsupported extension.
    """
    import tempfile

    all_sources = [input_path]
    if merge_paths:
        all_sources.extend(merge_paths)

    if len(all_sources) == 1:
        # Single source — preprocess directly to output
        return _detect_and_preprocess(input_path, output_path)

    # Multiple sources — preprocess each to temp files, then merge
    all_entries: list[list[CalendarEntry]] = []
    for source_path in all_sources:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            count = _detect_and_preprocess(source_path, tmp_path)
            logger.info("Preprocessed {} entries from {}", count, source_path)
            entries = parse_calendar_jsonl(tmp_path)
            all_entries.append(entries)
        finally:
            tmp_path.unlink(missing_ok=True)

    merged = _merge_entries(all_entries)

    if len(merged) == 0:
        logger.warning(
            "Calendar preprocessing produced 0 entries after merging {} source file(s). "
            "Check that source files contain valid calendar data.",
            len(all_sources),
        )

    # Write merged output
    with output_path.open("w", encoding="utf-8") as f:
        for entry in merged:
            record: dict[str, str | None] = {
                "election_name": entry.election_name,
                "election_date": str(entry.election_date),
            }
            if entry.registration_deadline:
                record["registration_deadline"] = str(entry.registration_deadline)
            if entry.early_voting_start:
                record["early_voting_start"] = str(entry.early_voting_start)
            if entry.early_voting_end:
                record["early_voting_end"] = str(entry.early_voting_end)
            if entry.absentee_request_deadline:
                record["absentee_request_deadline"] = str(entry.absentee_request_deadline)
            if entry.qualifying_start:
                record["qualifying_start"] = entry.qualifying_start.isoformat()
            if entry.qualifying_end:
                record["qualifying_end"] = entry.qualifying_end.isoformat()
            f.write(json.dumps(record) + "\n")

    logger.info("Wrote {} merged calendar entries to {}", len(merged), output_path)
    return len(merged)
