"""Unit tests for GeoJSON boundary reader."""

import json
from pathlib import Path

import pytest

from voter_api.lib.boundary_loader.geojson import read_geojson


class TestReadGeoJSON:
    """Tests for GeoJSON parsing."""

    def test_valid_geojson(self, tmp_path: Path) -> None:
        """Parse a valid GeoJSON FeatureCollection."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"NAME": "District 1", "GEOID": "01"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        }
        f = tmp_path / "test.geojson"
        f.write_text(json.dumps(geojson))

        boundaries = read_geojson(f)
        assert len(boundaries) == 1
        assert boundaries[0].name == "District 1"
        assert boundaries[0].boundary_identifier == "01"

    def test_polygon_to_multipolygon(self, tmp_path: Path) -> None:
        """Single Polygon is converted to MultiPolygon."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"NAME": "Test"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        }
        f = tmp_path / "test.geojson"
        f.write_text(json.dumps(geojson))

        boundaries = read_geojson(f)
        assert boundaries[0].geometry.geom_type == "MultiPolygon"

    def test_multipolygon_passthrough(self, tmp_path: Path) -> None:
        """MultiPolygon is kept as-is."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"NAME": "Multi"},
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
                    },
                }
            ],
        }
        f = tmp_path / "test.geojson"
        f.write_text(json.dumps(geojson))

        boundaries = read_geojson(f)
        assert boundaries[0].geometry.geom_type == "MultiPolygon"

    def test_empty_features_raises(self, tmp_path: Path) -> None:
        """Empty FeatureCollection raises ValueError."""
        f = tmp_path / "empty.geojson"
        f.write_text(json.dumps({"type": "FeatureCollection", "features": []}))

        with pytest.raises(ValueError, match="no features"):
            read_geojson(f)

    def test_wrong_type_raises(self, tmp_path: Path) -> None:
        """Non-FeatureCollection type raises ValueError."""
        f = tmp_path / "wrong.geojson"
        f.write_text(json.dumps({"type": "Feature", "properties": {}}))

        with pytest.raises(ValueError, match="FeatureCollection"):
            read_geojson(f)

    def test_properties_extracted(self, tmp_path: Path) -> None:
        """Feature properties are extracted."""
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"NAME": "Test", "GEOID": "42", "POPULATION": 1000},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        }
        f = tmp_path / "test.geojson"
        f.write_text(json.dumps(geojson))

        boundaries = read_geojson(f)
        assert boundaries[0].properties["POPULATION"] == 1000


class TestLoadBoundaries:
    """Tests for format auto-detection."""

    def test_geojson_extension(self, tmp_path: Path) -> None:
        """GeoJSON file detected by .geojson extension."""
        from voter_api.lib.boundary_loader import load_boundaries

        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"NAME": "X"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                    },
                }
            ],
        }
        f = tmp_path / "test.geojson"
        f.write_text(json.dumps(geojson))

        boundaries = load_boundaries(f)
        assert len(boundaries) == 1

    def test_unsupported_format(self, tmp_path: Path) -> None:
        """Unsupported format raises ValueError."""
        from voter_api.lib.boundary_loader import load_boundaries

        f = tmp_path / "test.xyz"
        f.write_text("data")

        with pytest.raises(ValueError, match="Unsupported"):
            load_boundaries(f)
