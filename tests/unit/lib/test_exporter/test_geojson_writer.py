"""Tests for the GeoJSON export writer."""

import json
from pathlib import Path

from voter_api.lib.exporter.geojson_writer import write_geojson


class TestGeoJSONWriter:
    """Tests for write_geojson."""

    def test_writes_feature_collection(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [
            {"voter_registration_number": "12345", "latitude": 33.749, "longitude": -84.388},
        ]
        count = write_geojson(output, records)
        assert count == 1

        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    def test_feature_geometry(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [{"latitude": 33.749, "longitude": -84.388, "name": "test"}]
        write_geojson(output, records)

        data = json.loads(output.read_text())
        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [-84.388, 33.749]

    def test_feature_properties(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [
            {
                "voter_registration_number": "12345",
                "county": "FULTON",
                "latitude": 33.749,
                "longitude": -84.388,
            },
        ]
        write_geojson(output, records)

        data = json.loads(output.read_text())
        props = data["features"][0]["properties"]
        assert props["voter_registration_number"] == "12345"
        assert props["county"] == "FULTON"
        # lat/lon should not be in properties
        assert "latitude" not in props
        assert "longitude" not in props

    def test_null_geometry_when_no_coords(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [{"voter_registration_number": "12345"}]
        write_geojson(output, records)

        data = json.loads(output.read_text())
        assert data["features"][0]["geometry"] is None

    def test_empty_records(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        count = write_geojson(output, [])
        assert count == 0

        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    def test_multiple_features(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [
            {"latitude": 33.749, "longitude": -84.388, "name": "A"},
            {"latitude": 34.0, "longitude": -84.5, "name": "B"},
        ]
        count = write_geojson(output, records)
        assert count == 2

        data = json.loads(output.read_text())
        assert len(data["features"]) == 2
