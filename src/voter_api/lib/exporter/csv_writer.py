"""CSV export writer for voter data."""

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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
            writer.writerow(record)
            count += 1

    return count
