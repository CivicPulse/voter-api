"""CSV loader for county-to-district mapping data.

Parses the state-provided CSV that maps Georgia counties to their
congressional, state senate, and state house districts.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

# Maps CSV column headers to boundary_type values
COLUMN_TO_BOUNDARY_TYPE: dict[str, str] = {
    "Congressional Districts": "congressional",
    "Senate Districts": "state_senate",
    "House Districts": "state_house",
}


@dataclass(frozen=True)
class CountyDistrictRecord:
    """A single county-to-district mapping."""

    county_name: str
    boundary_type: str
    district_identifier: str


def parse_county_districts_csv(file_path: Path) -> list[CountyDistrictRecord]:
    """Parse a county-to-district CSV file.

    Handles:
    - Comma-separated district numbers within cells (e.g., "142, 143, 144")
    - Multi-row counties where district lists are split across rows
    - Deduplication of records

    Args:
        file_path: Path to the CSV file.

    Returns:
        Sorted, deduplicated list of CountyDistrictRecord objects.

    Raises:
        ValueError: If the CSV is missing expected columns.
    """
    logger.info(f"Parsing county-district CSV: {file_path}")

    seen: set[tuple[str, str, str]] = set()
    records: list[CountyDistrictRecord] = []

    with Path.open(file_path, newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            msg = f"CSV file has no header row: {file_path}"
            raise ValueError(msg)

        # Validate expected columns exist
        missing = set(COLUMN_TO_BOUNDARY_TYPE.keys()) - set(reader.fieldnames)
        if missing:
            msg = f"CSV missing expected columns: {missing}"
            raise ValueError(msg)

        for row in reader:
            county_name = row["County"].strip().upper()
            if not county_name:
                continue

            for col_header, boundary_type in COLUMN_TO_BOUNDARY_TYPE.items():
                raw_value = row.get(col_header, "").strip()
                if not raw_value:
                    continue

                for district_num in _parse_district_numbers(raw_value):
                    key = (county_name, boundary_type, district_num)
                    if key not in seen:
                        seen.add(key)
                        records.append(
                            CountyDistrictRecord(
                                county_name=county_name,
                                boundary_type=boundary_type,
                                district_identifier=district_num,
                            )
                        )

    records.sort(key=lambda r: (r.county_name, r.boundary_type, r.district_identifier))
    logger.info(f"Parsed {len(records)} county-district mappings")
    return records


def _parse_district_numbers(raw: str) -> list[str]:
    """Parse a comma-separated string of district numbers.

    Handles formats like "1", "2, 8", "142, 143, 144, 145, 149",
    and trailing commas from multi-row splits.

    Args:
        raw: Raw cell value from the CSV.

    Returns:
        List of stripped district number strings.
    """
    return [num.strip() for num in raw.split(",") if num.strip()]
