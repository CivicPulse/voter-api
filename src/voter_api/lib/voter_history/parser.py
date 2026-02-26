"""GA SoS voter history CSV parser with chunked reading.

Parses the 9-column voter history format: County Name, Voter Registration Number,
Election Date, Election Type, Party, Ballot Style, Absentee, Provisional, Supplemental.
"""

from collections.abc import Iterator
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
# Used for joins to the elections table.
ELECTION_TYPE_MAP: dict[str, str] = {
    "GENERAL": "general",
    "GENERAL ELECTION": "general",
    "GENERAL PRIMARY": "primary",
    "GENERAL PRIMARY RUNOFF": "runoff",
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

    # Pre-compute the uppercase election type map for vectorized lookup
    upper_type_map = {k.upper(): v for k, v in ELECTION_TYPE_MAP.items()}

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

        # Replace empty strings with None (NaN in pandas)
        chunk = chunk.replace("", None)

        yield _process_chunk_vectorized(chunk, upper_type_map)


def _process_chunk_vectorized(
    chunk: pd.DataFrame,
    upper_type_map: dict[str, str],
) -> list[dict]:
    """Process a DataFrame chunk using vectorized pandas operations.

    Args:
        chunk: DataFrame with mapped column names and empty strings replaced by NaN.
        upper_type_map: Pre-computed uppercase election type mapping.

    Returns:
        List of parsed record dicts with ``_parse_error`` key.
    """
    n = len(chunk)
    errors = pd.Series([None] * n, index=chunk.index)

    # --- Required field validation (vectorized) ---
    required_fields = ["voter_registration_number", "county", "election_date", "election_type"]
    for field in required_fields:
        missing_mask = chunk[field].isna() if field in chunk.columns else pd.Series(True, index=chunk.index)
        # Only set error for rows that don't already have one
        new_errors = missing_mask & errors.isna()
        errors = errors.where(~new_errors, f"Missing {field}")

    # --- Date parsing (vectorized) ---
    if "election_date" in chunk.columns:
        has_date = chunk["election_date"].notna()
    else:
        has_date = pd.Series(False, index=chunk.index)
    no_error_yet = errors.isna()
    parseable_mask = has_date & no_error_yet

    parsed_dates = pd.Series([None] * n, index=chunk.index, dtype=object)
    if parseable_mask.any():
        date_strings = chunk.loc[parseable_mask, "election_date"].str.strip()
        converted = pd.to_datetime(date_strings, format="%m/%d/%Y", errors="coerce")
        # Set successfully parsed dates
        success_mask = converted.notna()
        parsed_dates.loc[success_mask.index[success_mask]] = converted[success_mask].dt.date
        # Mark bad dates as errors
        bad_date_mask = parseable_mask.copy()
        bad_date_mask.loc[success_mask.index[success_mask]] = False
        bad_date_idx = bad_date_mask[bad_date_mask].index
        if len(bad_date_idx) > 0:
            errors.loc[bad_date_idx] = "Invalid date format: " + chunk.loc[bad_date_idx, "election_date"]

    # --- Boolean parsing (vectorized) ---
    bool_fields = ["absentee", "provisional", "supplemental"]
    bool_results: dict[str, pd.Series] = {}
    for field in bool_fields:
        if field in chunk.columns:
            bool_results[field] = chunk[field].fillna("").str.strip().str.upper().eq("Y")
        else:
            bool_results[field] = pd.Series(False, index=chunk.index)

    # --- Election type normalization (vectorized) ---
    if "election_type" in chunk.columns:
        normalized_type = (
            chunk["election_type"].fillna("").str.strip().str.upper().map(upper_type_map).fillna(DEFAULT_ELECTION_TYPE)
        )
    else:
        normalized_type = pd.Series(DEFAULT_ELECTION_TYPE, index=chunk.index)

    # --- Registration number normalization (vectorized) ---
    if "voter_registration_number" in chunk.columns:
        raw_reg = chunk["voter_registration_number"]
        # Only normalize non-null values; preserve NaN for missing entries
        stripped = raw_reg.str.lstrip("0")
        # All-zeros → "0"; missing/NaN stays NaN
        normalized_reg = stripped.where(stripped != "", other="0").where(raw_reg.notna())
    else:
        normalized_reg = pd.Series("", index=chunk.index)

    # --- Build result dicts ---
    records: list[dict] = []
    # Convert columns to plain Python lists for fast iteration
    reg_list = normalized_reg.tolist()
    county_list = chunk["county"].tolist() if "county" in chunk.columns else [None] * n
    date_list = parsed_dates.tolist()
    raw_type_list = chunk["election_type"].tolist() if "election_type" in chunk.columns else [None] * n
    norm_type_list = normalized_type.tolist()
    party_list = chunk["party"].tolist() if "party" in chunk.columns else [None] * n
    ballot_list = chunk["ballot_style"].tolist() if "ballot_style" in chunk.columns else [None] * n
    abs_list = bool_results["absentee"].tolist()
    prov_list = bool_results["provisional"].tolist()
    supp_list = bool_results["supplemental"].tolist()
    error_list = errors.tolist()

    for i in range(n):
        # Normalize NaN → None for optional string fields
        county_val = county_list[i]
        if pd.isna(county_val):
            county_val = None
        raw_type_val = raw_type_list[i]
        if pd.isna(raw_type_val):
            raw_type_val = None
        party_val = party_list[i]
        party_val = None if pd.isna(party_val) else (party_val or None)
        ballot_val = ballot_list[i]
        ballot_val = None if pd.isna(ballot_val) else (ballot_val or None)
        reg_val = reg_list[i]
        if pd.isna(reg_val):
            reg_val = None

        records.append(
            {
                "voter_registration_number": reg_val,
                "county": county_val,
                "election_date": date_list[i],
                "election_type": raw_type_val,
                "normalized_election_type": norm_type_list[i],
                "party": party_val,
                "ballot_style": ballot_val,
                "absentee": abs_list[i],
                "provisional": prov_list[i],
                "supplemental": supp_list[i],
                "_parse_error": error_list[i],
            }
        )

    return records
