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


def _format_unknown_column_bug_report(
    file_path: Path,
    unknown_columns: list[str],
    actual_columns: list[str],
) -> str:
    """Format a copy-paste-ready GitHub issue body for unexpected CSV columns.

    Args:
        file_path: Path to the CSV file that triggered the error.
        unknown_columns: Column headers found in the file that are not in GA_SOS_COLUMN_MAP.
        actual_columns: All column headers found in the file.

    Returns:
        A formatted bug report string suitable for pasting into a GitHub issue.
    """
    unknown_list = "\n".join(f"  - {col!r}" for col in unknown_columns)
    actual_list = "\n".join(f"  - {col}" for col in actual_columns)
    known_list = "\n".join(f"  - {col}" for col in GA_SOS_COLUMN_MAP)

    return (
        "\n"
        "================================================================\n"
        "BUG REPORT — Unexpected column(s) in GA SoS voter CSV\n"
        "================================================================\n"
        "Import halted to prevent data loss. The source file contains\n"
        "column header(s) not recognized by the parser. This likely means\n"
        "the GA Secretary of State changed the voter file format.\n"
        "\n"
        "Please file a GitHub issue and paste this entire message:\n"
        "  https://github.com/CivicPulse/voter-api/issues/new\n"
        "\n"
        f"File: {file_path}\n"
        "\n"
        f"Unknown / unrecognized column(s) ({len(unknown_columns)}):\n"
        f"{unknown_list}\n"
        "\n"
        f"All column headers found in file ({len(actual_columns)}):\n"
        f"{actual_list}\n"
        "\n"
        f"Known columns in GA_SOS_COLUMN_MAP ({len(GA_SOS_COLUMN_MAP)}):\n"
        f"{known_list}\n"
        "================================================================\n"
    )


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
        ValueError: If the file contains column headers not recognized by
            GA_SOS_COLUMN_MAP (even after case-insensitive matching). The
            exception message contains a copy-paste-ready bug report for
            filing a GitHub issue. Import is halted immediately to prevent
            data loss from an unexpected file format change.
        ValueError: If the file cannot be parsed (bad delimiter or encoding).
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
            # Build rename map on the first chunk; emit per-file diagnostics.
            # GA SoS files occasionally deliver headers in all-caps or mixed case;
            # case-insensitive fallback handles that without discarding data.
            # Columns that are completely unrecognized halt the import immediately
            # so that format changes are caught and reported rather than silently
            # producing incomplete records.
            rename_map = {}
            unknown_columns: list[str] = []

            for csv_col in chunk.columns:
                if csv_col in GA_SOS_COLUMN_MAP:
                    rename_map[csv_col] = GA_SOS_COLUMN_MAP[csv_col]
                elif csv_col.lower() in _GA_SOS_COLUMN_MAP_LOWER:
                    rename_map[csv_col] = _GA_SOS_COLUMN_MAP_LOWER[csv_col.lower()]
                    logger.warning(
                        f"CSV column {csv_col!r} matched via case-insensitive fallback to field "
                        f"{_GA_SOS_COLUMN_MAP_LOWER[csv_col.lower()]!r}. "
                        "Add the exact-case header to GA_SOS_COLUMN_MAP to suppress this warning."
                    )
                else:
                    unknown_columns.append(csv_col)

            if unknown_columns:
                bug_report = _format_unknown_column_bug_report(
                    file_path,
                    unknown_columns,
                    list(chunk.columns),
                )
                raise ValueError(bug_report)

        chunk = chunk.rename(columns=rename_map)

        # Keep only mapped columns
        known_columns = [c for c in chunk.columns if c in GA_SOS_COLUMN_MAP.values()]
        chunk = chunk[known_columns]

        # Replace empty strings with NaN (pandas internal representation)
        chunk = chunk.replace("", None)

        yield chunk
