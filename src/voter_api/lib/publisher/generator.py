"""GeoJSON generation from boundary feature dicts.

Generates GeoJSON FeatureCollection files from pre-converted boundary
feature dicts. Matches the structure of the existing /api/v1/boundaries/geojson
endpoint output.
"""

import json
from pathlib import Path
from typing import Any

from loguru import logger


def generate_boundary_geojson(boundaries: list[dict[str, Any]], output_path: Path) -> int:
    """Write boundary features as a GeoJSON FeatureCollection.

    Takes boundary feature dicts (pre-converted from ORM objects by the
    service layer) and writes them to a GeoJSON file using streaming writes.

    Args:
        boundaries: List of GeoJSON feature dicts with type, id, geometry,
            and properties (name, boundary_type, boundary_identifier, source, county).
        output_path: Path to write the GeoJSON file.

    Returns:
        Number of features written.
    """
    count = 0

    with output_path.open("w", encoding="utf-8") as f:
        f.write('{"type": "FeatureCollection", "features": [\n')

        for i, feature in enumerate(boundaries):
            geometry = feature.get("geometry")
            if geometry is None:
                logger.warning(
                    "Skipping boundary with missing geometry: id={}",
                    feature.get("id", "unknown"),
                )
                continue

            if i > 0 and count > 0:
                f.write(",\n")

            try:
                json.dump(feature, f, default=str)
                count += 1
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Skipping boundary with invalid geometry: id={}, error={}",
                    feature.get("id", "unknown"),
                    exc,
                )

        f.write("\n]}\n")

    return count
