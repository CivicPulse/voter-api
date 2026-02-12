"""Shapefile reader using GeoPandas with pyogrio engine.

Reads .shp files, transforms CRS to EPSG:4326, and converts
geometries to MultiPolygon for consistent storage.
"""

from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
from loguru import logger
from shapely.geometry import MultiPolygon, Polygon


@dataclass
class BoundaryData:
    """Parsed boundary data ready for database storage."""

    name: str
    boundary_identifier: str
    geometry: MultiPolygon
    properties: dict = field(default_factory=dict)


def read_shapefile(file_path: Path) -> list[BoundaryData]:
    """Read a shapefile and return parsed boundary data.

    Transforms CRS to EPSG:4326 and converts all geometries to MultiPolygon.

    Args:
        file_path: Path to .shp file or directory containing .shp file.

    Returns:
        List of BoundaryData objects.

    Raises:
        ValueError: If the file cannot be read or has no geometry.
    """
    logger.info(f"Reading shapefile: {file_path}")

    gdf = gpd.read_file(file_path, engine="pyogrio")

    if gdf.empty:
        msg = f"Shapefile is empty: {file_path}"
        raise ValueError(msg)

    # Transform CRS to WGS84 (EPSG:4326)
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        logger.debug(f"Transforming CRS from {gdf.crs} to EPSG:4326")
        gdf = gdf.to_crs(epsg=4326)

    boundaries: list[BoundaryData] = []

    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None:
            continue

        # Convert to MultiPolygon if needed
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        elif not isinstance(geom, MultiPolygon):
            logger.warning(f"Skipping unsupported geometry type: {geom.geom_type}")
            continue

        # Extract properties (all non-geometry columns)
        props = {col: _serialize_value(row[col]) for col in gdf.columns if col != "geometry" and row[col] is not None}

        # Try to find name and identifier from common column patterns
        name = _extract_field(row, ["NAME", "Name", "name", "NAMELSAD", "DISTRICT"])
        identifier = _extract_field(row, ["GEOID", "DISTRICT", "DISTRICTID", "ID", "PREC_ID", "PRECINCT"])

        boundaries.append(
            BoundaryData(
                name=name or f"Boundary {len(boundaries) + 1}",
                boundary_identifier=identifier or str(len(boundaries) + 1),
                geometry=geom,
                properties=props,
            )
        )

    logger.info(f"Parsed {len(boundaries)} boundaries from shapefile")
    return boundaries


def _extract_field(row: object, candidates: list[str]) -> str | None:
    """Try to extract a field value from common column name patterns."""
    for col in candidates:
        val = getattr(row, col, None) if hasattr(row, col) else None
        if val is not None and str(val).strip():
            return str(val).strip()
    return None


def _serialize_value(val: object) -> object:
    """Serialize a GeoDataFrame value to JSON-safe type."""
    import numpy as np

    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, np.ndarray):
        return val.tolist()
    return val
