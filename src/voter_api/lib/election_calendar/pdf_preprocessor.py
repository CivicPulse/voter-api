"""Preprocessor for GA SoS PDF election calendar files.

Extracts election calendar data from PDF calendar documents published
by the Georgia Secretary of State Elections Division using ``pdfplumber``
table extraction.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

from loguru import logger


def _parse_date_flex(value: str) -> date | None:
    """Parse a date in MM/DD/YYYY or MM/DD/YY format.

    Args:
        value: Date string.

    Returns:
        Parsed date or None.
    """
    value = value.strip()
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if match:
        try:
            return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
        except ValueError:
            return None
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", value)
    if match:
        try:
            return date(2000 + int(match.group(3)), int(match.group(1)), int(match.group(2)))
        except ValueError:
            return None
    return None


def _parse_advance_voting_range(text: str) -> tuple[date | None, date | None]:
    """Extract start and end dates from advance voting text.

    Args:
        text: Advance voting dates text from the PDF table.

    Returns:
        Tuple of (start_date, end_date).
    """
    date_patterns = re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
    if len(date_patterns) >= 2:
        return _parse_date_flex(date_patterns[0]), _parse_date_flex(date_patterns[1])
    if len(date_patterns) == 1:
        return _parse_date_flex(date_patterns[0]), None
    return None, None


def _parse_registration_deadline(text: str) -> date | None:
    """Extract the primary (non-federal) registration deadline.

    Args:
        text: Registration deadline text, possibly with ``*`` federal line.

    Returns:
        The primary registration deadline date.
    """
    lines = text.strip().splitlines()
    for line in lines:
        line = line.strip()
        if line.startswith("*"):
            continue
        parsed = _parse_date_flex(line)
        if parsed is not None:
            return parsed
    # Fallback: first date found on a non-starred line
    for line in lines:
        line = line.strip()
        if line.startswith("*"):
            continue
        for dp in re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", line):
            parsed = _parse_date_flex(dp)
            if parsed is not None:
                return parsed
    return None


def _extract_qualifying_period(tables: list[list[list[str | None]]]) -> tuple[datetime | None, datetime | None]:
    """Search tables for the qualifying period date range.

    Looks for rows containing ``QUALIFYING`` and extracts the associated
    date range (e.g., ``"MARCH 2, 2026 - MARCH 6, 2026"``).

    Args:
        tables: All tables extracted from the PDF page.

    Returns:
        Tuple of (qualifying_start, qualifying_end) as datetimes.
    """
    for table in tables:
        for row in table:
            row_text = " ".join(str(c or "") for c in row)
            if "QUALIFYING" not in row_text.upper():
                continue

            # Look for "MONTH DD, YYYY" patterns
            month_date_matches = re.findall(
                r"(?:MARCH|JANUARY|FEBRUARY|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)"
                r"\s+\d{1,2},?\s+\d{4}",
                row_text,
                re.IGNORECASE,
            )
            if len(month_date_matches) >= 2:
                try:
                    start_str = month_date_matches[0].replace(",", "")
                    end_str = month_date_matches[1].replace(",", "")
                    q_start = datetime.strptime(start_str, "%B %d %Y")  # noqa: DTZ007
                    q_end = datetime.strptime(end_str, "%B %d %Y").replace(  # noqa: DTZ007
                        hour=23, minute=59, second=59
                    )
                    return q_start, q_end
                except ValueError:
                    pass

            # Try MM/DD/YYYY format
            date_patterns = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", row_text)
            if len(date_patterns) >= 2:
                d1 = _parse_date_flex(date_patterns[0])
                d2 = _parse_date_flex(date_patterns[1])
                if d1 and d2:
                    return (
                        datetime.combine(d1, datetime.min.time()),  # noqa: DTZ007
                        datetime.combine(d2, datetime.max.time().replace(microsecond=0)),  # noqa: DTZ007
                    )

    return None, None


def _is_data_row(row: list[str | None]) -> bool:
    """Check if a table row contains election data (not headers/blanks).

    Args:
        row: A row from the extracted PDF table.

    Returns:
        True if the row appears to contain election data.
    """
    non_empty = [str(c or "").strip() for c in row if str(c or "").strip()]
    if len(non_empty) < 2:
        return False
    row_text = " ".join(non_empty).upper()
    # Skip header rows
    if "ELECTION DATE" in row_text or "ADVANCE VOTING" in row_text:
        return False
    if "QUALIFYING PERIOD" in row_text or "GENERAL ELECTION CYCLE" in row_text:
        return False
    # Must contain at least one date pattern
    return bool(re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", row_text))


def preprocess_pdf_calendar(
    input_path: Path,
    output_path: Path,
) -> int:
    """Extract election calendar data from a GA SoS PDF calendar.

    Uses ``pdfplumber`` to extract tables from the PDF. Identifies election
    rows by looking for date patterns, and extracts election name, date,
    advance voting range, and registration deadline.

    Args:
        input_path: Path to the source PDF file.
        output_path: Path for the JSONL output file.

    Returns:
        Number of calendar entries written.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """
    import pdfplumber

    entries: list[dict] = []

    with pdfplumber.open(input_path) as pdf:
        all_tables: list[list[list[str | None]]] = []
        for page in pdf.pages:
            page_tables = page.extract_tables()
            all_tables.extend(page_tables)

        # Extract qualifying period
        qualifying_start, qualifying_end = _extract_qualifying_period(all_tables)

        for table in all_tables:
            # Collect data rows, merging continuation lines
            merged_rows: list[list[str]] = []
            for row in table:
                if not _is_data_row(row):
                    # Check if this is a continuation of the previous row
                    if merged_rows:
                        non_empty = [str(c or "").strip() for c in row if str(c or "").strip()]
                        skip_kws = ["ELECTION", "QUALIFYING", "DEADLINE"]
                        row_upper = " ".join(non_empty).upper()
                        if non_empty and not any(kw in row_upper for kw in skip_kws):
                            # Append text to previous row's cells
                            for i, cell in enumerate(row):
                                if cell and i < len(merged_rows[-1]):
                                    merged_rows[-1][i] = (merged_rows[-1][i] + "\n" + str(cell)).strip()
                    continue
                merged_rows.append([str(c or "").strip() for c in row])

            for row_vals in merged_rows:
                # Find the cell with the election date (MM/DD/YYYY with 4-digit year)
                election_date = None
                date_col_idx = None
                for i, val in enumerate(row_vals):
                    date_match = re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", val)
                    if date_match:
                        parsed = _parse_date_flex(date_match.group())
                        if parsed is not None:
                            election_date = parsed
                            date_col_idx = i
                            break

                if election_date is None:
                    continue

                # Election name is typically in cells before the date column
                name_parts = []
                for i in range(date_col_idx):  # type: ignore[arg-type]
                    val = row_vals[i].strip()
                    if val:
                        name_parts.append(val)
                election_name = " ".join(name_parts).replace("\n", " ").strip()
                if not election_name:
                    continue

                # Look for advance voting dates (cells after the date)
                early_start = None
                early_end = None
                reg_deadline = None
                for i in range(date_col_idx + 1, len(row_vals)):  # type: ignore[operator]
                    val = row_vals[i]
                    if not val:
                        continue
                    dates_in_cell = re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", val)
                    if len(dates_in_cell) >= 2 and early_start is None:
                        early_start, early_end = _parse_advance_voting_range(val)
                    elif dates_in_cell and reg_deadline is None and early_start is not None:
                        reg_deadline = _parse_registration_deadline(val)
                    elif dates_in_cell and early_start is None:
                        early_start, early_end = _parse_advance_voting_range(val)

                entry: dict[str, str] = {
                    "election_name": election_name,
                    "election_date": str(election_date),
                }
                if reg_deadline:
                    entry["registration_deadline"] = str(reg_deadline)
                if early_start:
                    entry["early_voting_start"] = str(early_start)
                if early_end:
                    entry["early_voting_end"] = str(early_end)
                if qualifying_start:
                    entry["qualifying_start"] = qualifying_start.isoformat()
                if qualifying_end:
                    entry["qualifying_end"] = qualifying_end.isoformat()

                entries.append(entry)
                logger.debug("Extracted PDF entry: {} on {}", election_name, election_date)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    logger.info("Wrote {} calendar entries from PDF to {}", len(entries), output_path)
    return len(entries)
