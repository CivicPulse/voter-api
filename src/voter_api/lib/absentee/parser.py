"""GA SoS absentee ballot application CSV parser with chunked reading.

Parses the 38-column absentee ballot application format exported by the
Georgia Secretary of State. Handles column mapping, date parsing, boolean
conversion, and registration number normalization.
"""

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from loguru import logger

from voter_api.lib.csv_utils import (
    detect_delimiter,
    detect_encoding,
    normalize_registration_number,
    parse_date_mdy,
)

# GA SoS absentee ballot 38-column mapping: CSV header → model field name
GA_SOS_ABSENTEE_COLUMN_MAP: dict[str, str] = {
    "County": "county",
    "Voter Registration #": "voter_registration_number",
    "Last Name": "last_name",
    "First Name": "first_name",
    "Middle Name": "middle_name",
    "Suffix": "suffix",
    "Street #": "street_number",
    "Street Name": "street_name",
    "Apt/Unit": "apt_unit",
    "City": "city",
    "State": "state",
    "Zip Code": "zip_code",
    "Mailing Street #": "mailing_street_number",
    "Mailing Street Name": "mailing_street_name",
    "Mailing Apt/Unit": "mailing_apt_unit",
    "Mailing City": "mailing_city",
    "Mailing State": "mailing_state",
    "Mailing Zip Code": "mailing_zip_code",
    "Application Status": "application_status",
    "Ballot Status": "ballot_status",
    "Status Reason": "status_reason",
    "Application Date": "application_date",
    "Ballot Issued Date": "ballot_issued_date",
    "Ballot Return Date": "ballot_return_date",
    "Ballot Style": "ballot_style",
    "Ballot Assisted": "ballot_assisted",
    "Challenged/Provisional": "challenged_provisional",
    "ID Required": "id_required",
    "Municipal Precinct": "municipal_precinct",
    "County Precinct": "county_precinct",
    "CNG": "congressional_district",
    "SEN": "state_senate_district",
    "HOUSE": "state_house_district",
    "JUD": "judicial_district",
    "Combo #": "combo",
    "Vote Center ID": "vote_center_id",
    "Ballot ID": "ballot_id",
    "Party": "party",
}

# Fields in the mapped output that correspond to model field names
_MAPPED_FIELDS: set[str] = set(GA_SOS_ABSENTEE_COLUMN_MAP.values())

# Date fields to parse (MM/DD/YYYY → date)
_DATE_FIELDS: list[str] = ["application_date", "ballot_issued_date", "ballot_return_date"]

# Boolean fields (YES/NO → True/False)
_BOOL_FIELDS: list[str] = ["ballot_assisted", "challenged_provisional", "id_required"]

# Required fields — records missing these get a _parse_error
_REQUIRED_FIELDS: list[str] = ["voter_registration_number", "county"]


def _parse_yes_no_bool(value: str | None) -> bool | None:
    """Convert a YES/NO string to a boolean.

    GA SoS absentee files use full-word YES/NO rather than Y/N.

    Args:
        value: String value, typically ``"YES"`` or ``"NO"``.

    Returns:
        ``True`` for YES/Y, ``False`` for NO/N, ``None`` for empty/None.
    """
    if value is None:
        return None
    cleaned = value.strip().upper()
    if cleaned in ("YES", "Y"):
        return True
    if cleaned in ("NO", "N"):
        return False
    if cleaned == "":
        return None
    return None


def parse_absentee_csv_chunks(
    file_path: Path,
    batch_size: int = 1000,
) -> Iterator[list[dict]]:
    """Parse a GA SoS absentee ballot application CSV in chunks.

    Reads the 38-column absentee ballot format, maps columns to model field
    names, normalizes registration numbers, parses dates and booleans, and
    yields lists of record dicts.

    Args:
        file_path: Path to the CSV file.
        batch_size: Number of rows per chunk.

    Yields:
        Lists of parsed record dicts with normalized fields. Each dict
        includes a ``_parse_error`` key (``None`` if valid, error message
        string if invalid).
    """
    delimiter = detect_delimiter(file_path)
    encoding = detect_encoding(file_path)

    logger.info(
        f"Parsing absentee CSV {file_path} with delimiter={delimiter!r}, encoding={encoding}, batch_size={batch_size}"
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
            if csv_col in GA_SOS_ABSENTEE_COLUMN_MAP:
                rename_map[csv_col] = GA_SOS_ABSENTEE_COLUMN_MAP[csv_col]
        chunk = chunk.rename(columns=rename_map)

        # Keep only mapped columns
        known = [c for c in chunk.columns if c in _MAPPED_FIELDS]
        chunk = chunk[known]

        # Replace empty strings with None
        chunk = chunk.replace("", None)

        yield _process_chunk(chunk)


def _process_chunk(chunk: pd.DataFrame) -> list[dict]:
    """Process a single DataFrame chunk into a list of record dicts.

    Args:
        chunk: DataFrame with mapped column names and empty strings
            replaced by ``None``.

    Returns:
        List of parsed record dicts with ``_parse_error`` key.
    """
    records: list[dict] = []

    for _, row in chunk.iterrows():
        record: dict = {}
        parse_error: str | None = None

        # Copy all mapped fields, converting NaN to None
        for field in _MAPPED_FIELDS:
            if field in row.index:
                val = row[field]
                record[field] = None if pd.isna(val) else val
            else:
                record[field] = None

        # Required field validation
        for field in _REQUIRED_FIELDS:
            if record.get(field) is None:
                parse_error = f"Missing required field: {field}"
                break

        # Normalize voter registration number
        if record.get("voter_registration_number") is not None:
            record["voter_registration_number"] = normalize_registration_number(record["voter_registration_number"])

        # Parse date fields
        for field in _DATE_FIELDS:
            record[field] = parse_date_mdy(record.get(field))

        # Parse boolean fields
        for field in _BOOL_FIELDS:
            record[field] = _parse_yes_no_bool(record.get(field))

        record["_parse_error"] = parse_error
        records.append(record)

    return records
