"""GeoJSON export writer for voter data with point geometries."""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from voter_api.lib.exporter.json_writer import _JSONEncoder


def write_geojson(
    output_path: Path,
    records: Iterable[dict[str, Any]],
) -> int:
    """Write voter records as a GeoJSON FeatureCollection.

    Each voter becomes a Feature with a Point geometry from their
    primary geocoded location. Voter attributes are stored as
    Feature properties.

    Args:
        output_path: Path to write the GeoJSON file.
        records: Iterable of voter record dicts. Each should have
            'latitude' and 'longitude' keys for geometry, or
            'primary_latitude' and 'primary_longitude'.

    Returns:
        Number of features written.
    """
    count = 0

    with output_path.open("w", encoding="utf-8") as f:
        f.write('{"type": "FeatureCollection", "features": [\n')

        for i, record in enumerate(records):
            lat = record.get("latitude") or record.get("primary_latitude")
            lon = record.get("longitude") or record.get("primary_longitude")

            if lat is not None and lon is not None:
                geometry: dict[str, Any] = {
                    "type": "Point",
                    "coordinates": [float(lon), float(lat)],
                }
            else:
                geometry = None  # type: ignore[assignment]

            # Remove geometry fields from properties
            properties = {
                k: v
                for k, v in record.items()
                if k not in ("latitude", "longitude", "primary_latitude", "primary_longitude")
            }

            feature = {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            }

            if i > 0:
                f.write(",\n")
            json.dump(feature, f, cls=_JSONEncoder)
            count += 1

        f.write("\n]}\n")

    return count
