"""CSV parser with automatic delimiter/encoding detection and chunked reading.

Parses Georgia Secretary of State voter CSV files with support for
comma, pipe, and tab delimiters, and UTF-8/Latin-1 encoding.
"""

from collections.abc import Iterator
from pathlib import Path

import pandas as pd
from loguru import logger

# GA SoS 53-column voter file mapping: expected header → model field name
GA_SOS_COLUMN_MAP: dict[str, str] = {
    "County": "county",
    "Voter Registration #": "voter_registration_number",
    "Voter Registration Number": "voter_registration_number",
    "Status": "status",
    "Status Reason": "status_reason",
    "Last Name": "last_name",
    "First Name": "first_name",
    "Middle Name": "middle_name",
    "Suffix": "suffix",
    "Birth Year": "birth_year",
    "Residence Street Number": "residence_street_number",
    "Residence Pre Direction": "residence_pre_direction",
    "Residence Street Name": "residence_street_name",
    "Residence Street Type": "residence_street_type",
    "Residence Post Direction": "residence_post_direction",
    "Residence Apt/Unit Number": "residence_apt_unit_number",
    "Residence Apt Unit Number": "residence_apt_unit_number",
    "Residence City": "residence_city",
    "Residence Zipcode": "residence_zipcode",
    "Mailing Street Number": "mailing_street_number",
    "Mailing Street Name": "mailing_street_name",
    "Mailing Apt/Unit Number": "mailing_apt_unit_number",
    "Mailing Apt Unit Number": "mailing_apt_unit_number",
    "Mailing City": "mailing_city",
    "Mailing Zipcode": "mailing_zipcode",
    "Mailing State": "mailing_state",
    "Mailing Country": "mailing_country",
    "County Precinct": "county_precinct",
    "County Precinct Description": "county_precinct_description",
    "Municipal Precinct": "municipal_precinct",
    "Municipal Precinct Description": "municipal_precinct_description",
    "Congressional District": "congressional_district",
    "State Senate District": "state_senate_district",
    "State House District": "state_house_district",
    "Judicial District": "judicial_district",
    "County Commission District": "county_commission_district",
    "School Board District": "school_board_district",
    "City Council District": "city_council_district",
    "Municipal School Board District": "municipal_school_board_district",
    "Water Board District": "water_board_district",
    "Super Council District": "super_council_district",
    "Super Commissioner District": "super_commissioner_district",
    "Super School Board District": "super_school_board_district",
    "Fire District": "fire_district",
    "Municipality": "municipality",
    "Combo": "combo",
    "Land Lot": "land_lot",
    "Land District": "land_district",
    "Registration Date": "registration_date",
    "Race": "race",
    "Gender": "gender",
    "Last Modified Date": "last_modified_date",
    "Date Of Last Contact": "date_of_last_contact",
    "Date of Last Contact": "date_of_last_contact",
    "Last Party Voted": "last_party_voted",
    "Last Vote Date": "last_vote_date",
    "Voter Created Date": "voter_created_date",
}

# Case-insensitive fallback lookup — used when exact header match fails.
# Handles files that use all-caps, all-lowercase, or mixed-case headers.
# Note: GA_SOS_COLUMN_MAP intentionally contains two keys that lowercase to
# "date of last contact" ("Date Of Last Contact" / "Date of Last Contact");
# both map to the same field, so the collision is harmless.
_GA_SOS_COLUMN_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in GA_SOS_COLUMN_MAP.items()}

# Guard against future additions that lowercase to the same string but map to
# *different* model fields — that would cause one column to silently shadow the other.
assert all(
    GA_SOS_COLUMN_MAP[k] == _GA_SOS_COLUMN_MAP_LOWER[k.lower()]
    for k in GA_SOS_COLUMN_MAP
), "GA_SOS_COLUMN_MAP contains keys that lowercase to the same string but map to different values."


def detect_delimiter(file_path: Path) -> str:
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

    # Count delimiter candidates
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


def detect_encoding(file_path: Path) -> str:
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


def parse_csv_chunks(
    file_path: Path,
    batch_size: int = 1000,
) -> Iterator[pd.DataFrame]:
    """Parse a voter CSV file in chunks with automatic delimiter/encoding detection.

    Args:
        file_path: Path to the CSV file.
        batch_size: Number of rows per chunk.

    Yields:
        DataFrame chunks with columns mapped to model field names.

    Raises:
        ValueError: If the file cannot be parsed.
    """
    delimiter = detect_delimiter(file_path)
    encoding = detect_encoding(file_path)

    logger.info(f"Parsing {file_path} with delimiter={delimiter!r}, encoding={encoding}, batch_size={batch_size}")

    reader = pd.read_csv(
        file_path,
        sep=delimiter,
        encoding=encoding,
        chunksize=batch_size,
        dtype=str,
        keep_default_na=False,
    )

    # Column headers are constant within a file; build the rename map once from
    # the first chunk to avoid redundant work on every subsequent chunk.
    rename_map: dict[str, str] | None = None

    for chunk in reader:
        # Strip whitespace from column names
        chunk.columns = chunk.columns.str.strip()

        if rename_map is None:
            # Build rename map and emit per-file diagnostics on the first chunk.
            # GA SoS files occasionally deliver headers in all-caps or mixed case;
            # silently dropping those columns was the root cause of null district fields.
            rename_map = {}
            for csv_col in chunk.columns:
                if csv_col in GA_SOS_COLUMN_MAP:
                    rename_map[csv_col] = GA_SOS_COLUMN_MAP[csv_col]
                elif csv_col.lower() in _GA_SOS_COLUMN_MAP_LOWER:
                    rename_map[csv_col] = _GA_SOS_COLUMN_MAP_LOWER[csv_col.lower()]

            for csv_col in chunk.columns:
                if csv_col not in GA_SOS_COLUMN_MAP and csv_col.lower() in _GA_SOS_COLUMN_MAP_LOWER:
                    logger.warning(
                        f"CSV column {csv_col!r} matched via case-insensitive fallback to field "
                        f"{_GA_SOS_COLUMN_MAP_LOWER[csv_col.lower()]!r}. "
                        "Add the exact-case header to GA_SOS_COLUMN_MAP to suppress this warning."
                    )
                elif csv_col not in GA_SOS_COLUMN_MAP:
                    logger.debug(f"Ignoring unknown CSV column: {csv_col!r}")

        chunk = chunk.rename(columns=rename_map)

        # Keep only mapped columns
        known_columns = [c for c in chunk.columns if c in GA_SOS_COLUMN_MAP.values()]
        chunk = chunk[known_columns]

        # Replace empty strings with NaN (pandas internal representation)
        chunk = chunk.replace("", None)

        yield chunk
