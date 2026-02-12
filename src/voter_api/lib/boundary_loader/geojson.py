"""GeoJSON reader — parses .geojson files and converts geometries to MultiPolygon."""

import json
from pathlib import Path

from loguru import logger
from shapely.geometry import MultiPolygon, Polygon, shape

from voter_api.lib.boundary_loader.shapefile import BoundaryData


def read_geojson(file_path: Path) -> list[BoundaryData]:
    """Read a GeoJSON file and return parsed boundary data.

    Validates geometry and converts to MultiPolygon.

    Args:
        file_path: Path to .geojson or .json file.

    Returns:
        List of BoundaryData objects.

    Raises:
        ValueError: If the file cannot be parsed or has invalid geometry.
    """
    logger.info(f"Reading GeoJSON: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        msg = f"Expected FeatureCollection, got {data.get('type')}"
        raise ValueError(msg)

    features = data.get("features", [])
    if not features:
        msg = f"GeoJSON has no features: {file_path}"
        raise ValueError(msg)

    boundaries: list[BoundaryData] = []

    for i, feature in enumerate(features):
        geom_data = feature.get("geometry")
        if not geom_data:
            continue

        geom = shape(geom_data)

        # Convert to MultiPolygon
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        elif not isinstance(geom, MultiPolygon):
            logger.warning(f"Skipping unsupported geometry type: {geom.geom_type}")
            continue

        # Validate geometry
        if not geom.is_valid:
            logger.warning(f"Feature {i} has invalid geometry, attempting repair")
            geom = geom.buffer(0)
            if isinstance(geom, Polygon):
                geom = MultiPolygon([geom])

        props = feature.get("properties", {}) or {}

        name = props.get("NAME") or props.get("name") or props.get("NAMELSAD") or f"Boundary {i + 1}"
        identifier = (
            props.get("GEOID") or props.get("DISTRICT") or props.get("ID") or props.get("PREC_ID") or str(i + 1)
        )

        boundaries.append(
            BoundaryData(
                name=str(name),
                boundary_identifier=str(identifier),
                geometry=geom,
                properties=props,
            )
        )

    logger.info(f"Parsed {len(boundaries)} boundaries from GeoJSON")
    return boundaries
