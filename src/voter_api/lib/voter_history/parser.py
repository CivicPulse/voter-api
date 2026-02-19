"""GA SoS voter history CSV parser with chunked reading.

Parses the 9-column voter history format: County Name, Voter Registration Number,
Election Date, Election Type, Party, Ballot Style, Absentee, Provisional, Supplemental.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from loguru import logger

# GA SoS voter history 9-column mapping: CSV header → model field name
GA_SOS_VOTER_HISTORY_COLUMN_MAP: dict[str, str] = {
    "County Name": "county",
    "Voter Registration Number": "voter_registration_number",
    "Election Date": "election_date",
    "Election Type": "election_type",
    "Party": "party",
    "Ballot Style": "ballot_style",
    "Absentee": "absentee",
    "Provisional": "provisional",
    "Supplemental": "supplemental",
}

# Mapping from GA SoS verbose election types to normalized vocabulary.
# Used for election auto-creation and joins to the elections table.
ELECTION_TYPE_MAP: dict[str, str] = {
    "GENERAL ELECTION": "general",
    "GENERAL PRIMARY": "primary",
    "SPECIAL ELECTION": "special",
    "SPECIAL ELECTION RUNOFF": "runoff",
    "SPECIAL PRIMARY": "primary",
    "SPECIAL PRIMARY RUNOFF": "runoff",
    "PRESIDENTIAL PREFERENCE PRIMARY": "primary",
}

# Default normalized type for unknown election types
DEFAULT_ELECTION_TYPE = "general"


def map_election_type(raw_type: str) -> str:
    """Map a GA SoS election type string to the normalized vocabulary.

    Args:
        raw_type: Raw election type from CSV (e.g., "GENERAL ELECTION").

    Returns:
        Normalized election type (e.g., "general", "primary", "special", "runoff").
    """
    return ELECTION_TYPE_MAP.get(raw_type.strip().upper(), DEFAULT_ELECTION_TYPE)


def generate_election_name(raw_type: str, election_date: date) -> str:
    """Generate a human-readable election name for auto-created elections.

    Args:
        raw_type: Raw election type from CSV (e.g., "GENERAL ELECTION").
        election_date: The election date.

    Returns:
        Generated name (e.g., "General Election - 11/05/2024").
    """
    title = raw_type.strip().title()
    date_str = election_date.strftime("%m/%d/%Y")
    return f"{title} - {date_str}"


def _parse_date(value: str) -> date | None:
    """Parse a date from MM/DD/YYYY format.

    Args:
        value: Date string in MM/DD/YYYY format.

    Returns:
        Parsed date or None if unparseable.
    """
    try:
        # We only need the date portion, so timezone is irrelevant
        return datetime.strptime(value.strip(), "%m/%d/%Y").date()  # noqa: DTZ007
    except (ValueError, AttributeError):
        return None


def _parse_bool(value: str | None) -> bool:
    """Parse a boolean flag: "Y" → True, anything else → False.

    Args:
        value: String value from CSV.

    Returns:
        True if value is "Y", False otherwise.
    """
    if value is None:
        return False
    return value.strip().upper() == "Y"


def _detect_delimiter(file_path: Path) -> str:
    """Detect the CSV delimiter by reading the first line.

    Args:
        file_path: Path to the CSV file.

    Returns:
        The detected delimiter character.

    Raises:
        ValueError: If the delimiter cannot be detected.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            with file_path.open("r", encoding=encoding) as f:
                first_line = f.readline()
            break
        except UnicodeDecodeError:
            continue
    else:
        msg = f"Cannot detect encoding for {file_path}"
        raise ValueError(msg)

    counts = {
        ",": first_line.count(","),
        "|": first_line.count("|"),
        "\t": first_line.count("\t"),
    }
    delimiter = max(counts, key=counts.get)  # type: ignore[arg-type]
    if counts[delimiter] == 0:
        msg = f"Cannot detect delimiter in {file_path}"
        raise ValueError(msg)

    logger.debug(f"Detected delimiter: {delimiter!r} for {file_path}")
    return delimiter


def _detect_encoding(file_path: Path) -> str:
    """Detect file encoding by attempting to read with common encodings.

    Args:
        file_path: Path to the CSV file.

    Returns:
        The detected encoding string.

    Raises:
        ValueError: If encoding cannot be detected.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            with file_path.open("r", encoding=encoding) as f:
                f.read(8192)
            return encoding
        except UnicodeDecodeError:
            continue
    msg = f"Cannot detect encoding for {file_path}"
    raise ValueError(msg)


def parse_voter_history_chunks(
    file_path: Path,
    batch_size: int = 1000,
) -> Iterator[list[dict]]:
    """Parse a voter history CSV file in chunks.

    Reads the GA SoS 9-column voter history format, maps columns to model
    field names, parses dates and booleans, and yields lists of record dicts.

    Args:
        file_path: Path to the CSV file.
        batch_size: Number of rows per chunk.

    Yields:
        Lists of parsed record dicts, each with an added
        ``normalized_election_type`` field and ``_parse_error`` key
        (None if valid, error message string if invalid).
    """
    delimiter = _detect_delimiter(file_path)
    encoding = _detect_encoding(file_path)

    logger.info(
        f"Parsing voter history {file_path} with delimiter={delimiter!r}, encoding={encoding}, batch_size={batch_size}"
    )

    reader = pd.read_csv(
        file_path,
        sep=delimiter,
        encoding=encoding,
        chunksize=batch_size,
        dtype=str,
        keep_default_na=False,
    )

    for chunk in reader:
        chunk.columns = chunk.columns.str.strip()

        # Map column names
        rename_map = {}
        for csv_col in chunk.columns:
            if csv_col in GA_SOS_VOTER_HISTORY_COLUMN_MAP:
                rename_map[csv_col] = GA_SOS_VOTER_HISTORY_COLUMN_MAP[csv_col]
        chunk = chunk.rename(columns=rename_map)

        # Keep only mapped columns
        known = [c for c in chunk.columns if c in GA_SOS_VOTER_HISTORY_COLUMN_MAP.values()]
        chunk = chunk[known]

        # Replace empty strings with None
        chunk = chunk.replace("", None)

        records: list[dict] = []
        for row in chunk.to_dict("records"):
            # pandas represents None as float NaN in dicts; normalize to Python None
            row = {k: (None if pd.isna(v) else v) for k, v in row.items()}
            record = _process_row(row)
            records.append(record)

        yield records


def _process_row(row: dict) -> dict:
    """Process a single CSV row into a validated record dict.

    Args:
        row: Raw row dict with mapped column names.

    Returns:
        Processed record dict with parsed fields and ``_parse_error`` key.
    """
    error: str | None = None

    # Required fields check
    reg_num = row.get("voter_registration_number")
    county = row.get("county")
    raw_date = row.get("election_date")
    raw_type = row.get("election_type")

    if not reg_num:
        error = "Missing voter_registration_number"
    elif not county:
        error = "Missing county"
    elif not raw_date:
        error = "Missing election_date"
    elif not raw_type:
        error = "Missing election_type"

    # Parse date
    parsed_date: date | None = None
    if raw_date and error is None:
        parsed_date = _parse_date(raw_date)
        if parsed_date is None:
            error = f"Invalid date format: {raw_date}"

    # Parse booleans
    absentee = _parse_bool(row.get("absentee"))
    provisional = _parse_bool(row.get("provisional"))
    supplemental = _parse_bool(row.get("supplemental"))

    # Normalize election type
    normalized = map_election_type(raw_type) if raw_type else DEFAULT_ELECTION_TYPE

    # Handle optional string fields
    party = row.get("party") if row.get("party") else None
    ballot_style = row.get("ballot_style") if row.get("ballot_style") else None

    return {
        "voter_registration_number": reg_num,
        "county": county,
        "election_date": parsed_date,
        "election_type": raw_type,
        "normalized_election_type": normalized,
        "party": party,
        "ballot_style": ballot_style,
        "absentee": absentee,
        "provisional": provisional,
        "supplemental": supplemental,
        "_parse_error": error,
    }
