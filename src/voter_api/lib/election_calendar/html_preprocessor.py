"""Preprocessor for GA SoS HTML election calendar pages.

Extracts election calendar data from HTML pages containing table-formatted
election calendars, using BeautifulSoup for parsing.
"""

import json
import re
from datetime import date
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
        return date(int(match.group(3)), int(match.group(1)), int(match.group(2)))
    match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2})", value)
    if match:
        return date(2000 + int(match.group(3)), int(match.group(1)), int(match.group(2)))
    return None


def _parse_advance_voting_range(text: str) -> tuple[date | None, date | None]:
    """Extract start and end dates from advance voting text.

    Args:
        text: Advance voting dates text.

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
    """Extract the primary registration deadline from text.

    Args:
        text: Registration deadline text.

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
    date_patterns = re.findall(r"\d{1,2}/\d{1,2}/\d{2,4}", text)
    for dp in date_patterns:
        parsed = _parse_date_flex(dp)
        if parsed is not None:
            return parsed
    return None


def preprocess_html_calendar(
    input_path: Path,
    output_path: Path,
) -> int:
    """Extract election calendar data from a GA SoS HTML page.

    Parses HTML tables looking for election calendar structures. Expects
    tables with columns for election name, election date, advance voting
    dates, and registration deadlines.

    Args:
        input_path: Path to the source HTML file.
        output_path: Path for the JSONL output file.

    Returns:
        Number of calendar entries written.

    Raises:
        FileNotFoundError: If the input file does not exist.
    """
    from bs4 import BeautifulSoup

    html_content = input_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html_content, "lxml")

    entries: list[dict] = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Try to identify header row
        header_row = None
        header_idx = -1
        for i, row in enumerate(rows):
            cells = row.find_all(["th", "td"])
            cell_texts = [c.get_text(strip=True).upper() for c in cells]
            joined = " ".join(cell_texts)
            if "ELECTION" in joined and "DATE" in joined:
                header_row = cell_texts
                header_idx = i
                break

        if header_row is None:
            continue

        # Map columns
        col_map: dict[str, int] = {}
        for i, text in enumerate(header_row):
            if "ADVANCE" in text or "VOTING" in text:
                col_map["advance_voting"] = i
            elif "REGISTRATION" in text or "DEADLINE" in text:
                col_map["registration"] = i
            elif "ELECTION" in text and "DATE" in text:
                col_map["date"] = i
            elif "ELECTION" in text:
                col_map["election"] = i

        if "election" not in col_map or "date" not in col_map:
            continue

        # Process data rows
        for row in rows[header_idx + 1 :]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= max(col_map.values()):
                continue

            cell_texts = [c.get_text(separator="\n", strip=True) for c in cells]

            election_name = cell_texts[col_map["election"]].replace("\n", " ").strip()
            if not election_name:
                continue

            date_text = cell_texts[col_map["date"]].strip()
            election_date = _parse_date_flex(date_text)
            if election_date is None:
                continue

            entry: dict[str, str] = {
                "election_name": election_name,
                "election_date": str(election_date),
            }

            if "advance_voting" in col_map:
                adv_text = cell_texts[col_map["advance_voting"]]
                early_start, early_end = _parse_advance_voting_range(adv_text)
                if early_start:
                    entry["early_voting_start"] = str(early_start)
                if early_end:
                    entry["early_voting_end"] = str(early_end)

            if "registration" in col_map:
                reg_text = cell_texts[col_map["registration"]]
                reg_deadline = _parse_registration_deadline(reg_text)
                if reg_deadline:
                    entry["registration_deadline"] = str(reg_deadline)

            entries.append(entry)
            logger.debug("Extracted HTML entry: {} on {}", election_name, election_date)

    with output_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    logger.info("Wrote {} calendar entries from HTML to {}", len(entries), output_path)
    return len(entries)
