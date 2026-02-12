"""Unit tests for publisher GeoJSON generator."""

import json
from pathlib import Path

from voter_api.lib.publisher.generator import generate_boundary_geojson


def _make_feature(
    feature_id: str = "test-id",
    name: str = "Test District",
    boundary_type: str = "congressional",
    boundary_identifier: str = "01",
    source: str = "state",
    county: str | None = None,
) -> dict:
    """Create a test GeoJSON feature dict."""
    return {
        "type": "Feature",
        "id": feature_id,
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
        },
        "properties": {
            "name": name,
            "boundary_type": boundary_type,
            "boundary_identifier": boundary_identifier,
            "source": source,
            "county": county,
        },
    }


class TestGenerateBoundaryGeojson:
    """Tests for generate_boundary_geojson."""

    def test_valid_boundaries_produce_feature_collection(self, tmp_path: Path) -> None:
        """Valid boundary dicts produce a GeoJSON FeatureCollection."""
        features = [_make_feature("id-1", "District 1"), _make_feature("id-2", "District 2")]
        output = tmp_path / "test.geojson"

        count = generate_boundary_geojson(features, output)

        assert count == 2
        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 2

    def test_feature_structure_matches_endpoint(self, tmp_path: Path) -> None:
        """Generated features match the /api/v1/boundaries/geojson structure."""
        feature = _make_feature(
            feature_id="abc-123",
            name="GA-01",
            boundary_type="congressional",
            boundary_identifier="01",
            source="state",
            county="Fulton",
        )
        output = tmp_path / "test.geojson"

        generate_boundary_geojson([feature], output)

        data = json.loads(output.read_text())
        f = data["features"][0]
        assert f["type"] == "Feature"
        assert f["id"] == "abc-123"
        assert f["geometry"]["type"] == "MultiPolygon"
        props = f["properties"]
        assert props["name"] == "GA-01"
        assert props["boundary_type"] == "congressional"
        assert props["boundary_identifier"] == "01"
        assert props["source"] == "state"
        assert props["county"] == "Fulton"

    def test_streaming_write_produces_valid_json(self, tmp_path: Path) -> None:
        """Streaming write produces valid JSON that can be parsed."""
        features = [_make_feature(f"id-{i}") for i in range(100)]
        output = tmp_path / "large.geojson"

        count = generate_boundary_geojson(features, output)

        assert count == 100
        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 100

    def test_invalid_geometries_are_skipped(self, tmp_path: Path) -> None:
        """Features with None geometry are skipped with a warning."""
        features = [
            _make_feature("id-1"),
            {"type": "Feature", "id": "bad-id", "geometry": None, "properties": {}},
            _make_feature("id-3"),
        ]
        output = tmp_path / "test.geojson"

        count = generate_boundary_geojson(features, output)

        assert count == 2
        data = json.loads(output.read_text())
        assert len(data["features"]) == 2

    def test_empty_input_produces_empty_collection(self, tmp_path: Path) -> None:
        """Empty input produces a valid FeatureCollection with no features."""
        output = tmp_path / "empty.geojson"

        count = generate_boundary_geojson([], output)

        assert count == 0
        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    def test_returns_record_count(self, tmp_path: Path) -> None:
        """Function returns the number of features written."""
        features = [_make_feature(f"id-{i}") for i in range(5)]
        output = tmp_path / "test.geojson"

        count = generate_boundary_geojson(features, output)

        assert count == 5
