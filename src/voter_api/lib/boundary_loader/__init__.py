"""Boundary loader library — imports shapefiles and GeoJSON boundary data.

Public API:
    - load_boundaries: Auto-detect format and parse boundary file
    - BoundaryData: Parsed boundary data structure
    - read_shapefile: Direct shapefile reader
    - read_geojson: Direct GeoJSON reader
    - verify_sha512: SHA512 checksum verification
    - BoundaryFileEntry: Manifest entry dataclass
    - BOUNDARY_MANIFEST: All boundary file entries
    - ImportResult: Import outcome tracker
    - find_shp_in_zip: Zip extraction + .shp locator
    - get_manifest: Get a copy of the manifest
    - resolve_zip_path: Resolve zip file path from data dir
"""

from pathlib import Path

from voter_api.lib.boundary_loader.checksum import verify_sha512
from voter_api.lib.boundary_loader.geojson import read_geojson
from voter_api.lib.boundary_loader.manifest import (
    BOUNDARY_MANIFEST,
    BoundaryFileEntry,
    ImportResult,
    find_shp_in_zip,
    get_manifest,
    resolve_zip_path,
)
from voter_api.lib.boundary_loader.shapefile import BoundaryData, read_shapefile


def load_boundaries(file_path: Path) -> list[BoundaryData]:
    """Load boundaries from a file with automatic format detection.

    Supports .shp (shapefile), .geojson, and .json (GeoJSON) formats.

    Args:
        file_path: Path to the boundary file.

    Returns:
        List of BoundaryData objects.

    Raises:
        ValueError: If the file format is not supported.
    """
    suffix = file_path.suffix.lower()

    if suffix == ".shp":
        return read_shapefile(file_path)
    if suffix in (".geojson", ".json"):
        return read_geojson(file_path)

    msg = f"Unsupported boundary file format: {suffix}. Supported: .shp, .geojson, .json"
    raise ValueError(msg)


__all__ = [
    "BOUNDARY_MANIFEST",
    "BoundaryData",
    "BoundaryFileEntry",
    "ImportResult",
    "find_shp_in_zip",
    "get_manifest",
    "load_boundaries",
    "read_geojson",
    "read_shapefile",
    "resolve_zip_path",
    "verify_sha512",
]
