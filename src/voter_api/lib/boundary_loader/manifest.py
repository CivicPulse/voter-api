"""Boundary file manifest — maps zip files to import metadata."""

import zipfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass(frozen=True)
class BoundaryFileEntry:
    """Metadata for a single boundary zip file."""

    zip_filename: str
    boundary_type: str
    source: str
    county: str | None = None
    description: str = ""
    state_fips: str | None = None


BOUNDARY_MANIFEST: list[BoundaryFileEntry] = [
    BoundaryFileEntry(
        zip_filename="congress-2023-shape.zip",
        boundary_type="congressional",
        source="state",
        description="US Congressional districts (GA)",
    ),
    BoundaryFileEntry(
        zip_filename="senate-2023-shape-file.zip",
        boundary_type="state_senate",
        source="state",
        description="GA State Senate districts",
    ),
    BoundaryFileEntry(
        zip_filename="house-2023-shape.zip",
        boundary_type="state_house",
        source="state",
        description="GA State House districts",
    ),
    BoundaryFileEntry(
        zip_filename="psc-2022.zip",
        boundary_type="psc",
        source="state",
        description="Public Service Commission districts",
    ),
    BoundaryFileEntry(
        zip_filename="tl_2025_us_county.zip",
        boundary_type="county",
        source="state",
        description="US Census county boundaries (filtered to GA)",
        state_fips="13",
    ),
    BoundaryFileEntry(
        zip_filename="gaprec_2024-website-shapefile.zip",
        boundary_type="county_precinct",
        source="state",
        description="GA county precinct boundaries",
    ),
    BoundaryFileEntry(
        zip_filename="bibbcc-2022-shape-file.zip",
        boundary_type="county_commission",
        source="county",
        county="Bibb",
        description="Bibb County commission districts",
    ),
    BoundaryFileEntry(
        zip_filename="bibbsb-2022-shape-file.zip",
        boundary_type="school_board",
        source="county",
        county="Bibb",
        description="Bibb County school board districts",
    ),
]


@dataclass
class ImportResult:
    """Tracks the outcome of importing a single boundary file."""

    entry: BoundaryFileEntry
    success: bool = False
    count: int = 0
    error: str | None = None


def get_manifest() -> list[BoundaryFileEntry]:
    """Return a copy of the boundary manifest.

    Returns:
        A new list containing all manifest entries.
    """
    return list(BOUNDARY_MANIFEST)


def resolve_zip_path(data_dir: Path, entry: BoundaryFileEntry) -> Path:
    """Resolve the full path to a zip file from the data directory.

    Args:
        data_dir: Directory containing boundary zip files.
        entry: Manifest entry with the zip filename.

    Returns:
        Full path to the zip file.
    """
    return data_dir / entry.zip_filename


def find_shp_in_zip(zip_path: Path, extract_dir: Path) -> Path:
    """Extract a zip file and locate the .shp file inside.

    Args:
        zip_path: Path to the zip archive.
        extract_dir: Directory to extract contents into.

    Returns:
        Path to the first .shp file found.

    Raises:
        ValueError: If the zip contains no .shp file.
        zipfile.BadZipFile: If the file is not a valid zip archive.
    """
    logger.debug(f"Extracting {zip_path.name} to {extract_dir}")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    shp_files = list(extract_dir.rglob("*.shp"))

    if not shp_files:
        msg = f"No .shp file found in {zip_path.name}"
        raise ValueError(msg)

    if len(shp_files) > 1:
        logger.warning(f"Multiple .shp files in {zip_path.name}, using first: {shp_files[0].name}")

    return shp_files[0]
