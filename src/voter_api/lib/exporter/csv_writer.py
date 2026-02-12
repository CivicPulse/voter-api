"""CSV export writer for voter data."""

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Characters that trigger formula execution in spreadsheet applications
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_cell(value: object) -> object:
    """Sanitize a cell value to prevent CSV formula injection.

    Prefixes values starting with formula-triggering characters with
    a single quote to prevent execution in spreadsheet applications.

    Args:
        value: The cell value to sanitize.

    Returns:
        The sanitized value.
    """
    if isinstance(value, str) and value and value[0] in _FORMULA_PREFIXES:
        return f"'{value}"
    return value


# Default columns for CSV export
DEFAULT_COLUMNS = [
    "voter_registration_number",
    "county",
    "status",
    "last_name",
    "first_name",
    "middle_name",
    "residence_street_number",
    "residence_street_name",
    "residence_street_type",
    "residence_city",
    "residence_zipcode",
    "congressional_district",
    "state_senate_district",
    "state_house_district",
    "county_precinct",
]


def write_csv(
    output_path: Path,
    records: Iterable[dict[str, Any]],
    *,
    columns: list[str] | None = None,
) -> int:
    """Write voter records to a CSV file.

    Args:
        output_path: Path to write the CSV file.
        records: Iterable of voter record dicts.
        columns: Column names to include. Defaults to DEFAULT_COLUMNS.

    Returns:
        Number of records written.
    """
    cols = columns or DEFAULT_COLUMNS
    count = 0

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()

        for record in records:
            sanitized = {k: _sanitize_cell(v) for k, v in record.items()}
            writer.writerow(sanitized)
            count += 1

    return count
