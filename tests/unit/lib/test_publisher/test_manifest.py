"""Unit tests for publisher manifest builder."""

from datetime import UTC, datetime

from voter_api.lib.publisher.manifest import build_manifest
from voter_api.lib.publisher.types import DatasetEntry


def _make_dataset_entry(
    name: str = "congressional",
    boundary_type: str | None = "congressional",
) -> DatasetEntry:
    """Create a test DatasetEntry."""
    return DatasetEntry(
        name=name,
        key=f"boundaries/{name}.geojson",
        public_url=f"https://geo.example.com/boundaries/{name}.geojson",
        content_type="application/geo+json",
        record_count=14,
        file_size_bytes=2340500,
        boundary_type=boundary_type,
        filters={"boundary_type": name} if boundary_type else {},
        published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
    )


class TestBuildManifest:
    """Tests for build_manifest."""

    def test_produces_correct_schema(self) -> None:
        """build_manifest produces correct schema with required fields."""
        datasets = [_make_dataset_entry()]

        result = build_manifest(datasets, "0.1.0")

        assert result["version"] == "1"
        assert "published_at" in result
        assert result["publisher_version"] == "0.1.0"
        assert "datasets" in result

    def test_datasets_keyed_by_name(self) -> None:
        """Datasets are keyed by dataset name in the manifest."""
        datasets = [
            _make_dataset_entry("congressional"),
            _make_dataset_entry("state_senate", "state_senate"),
        ]

        result = build_manifest(datasets, "0.1.0")

        assert "congressional" in result["datasets"]
        assert "state_senate" in result["datasets"]

    def test_dataset_entries_serialized_with_all_fields(self) -> None:
        """Dataset entries include all required fields."""
        datasets = [_make_dataset_entry()]

        result = build_manifest(datasets, "0.1.0")

        entry = result["datasets"]["congressional"]
        assert entry["key"] == "boundaries/congressional.geojson"
        assert entry["public_url"] == "https://geo.example.com/boundaries/congressional.geojson"
        assert entry["content_type"] == "application/geo+json"
        assert entry["record_count"] == 14
        assert entry["file_size_bytes"] == 2340500
        assert entry["boundary_type"] == "congressional"
        assert entry["filters"] == {"boundary_type": "congressional"}
        assert "published_at" in entry

    def test_empty_datasets_produces_valid_manifest(self) -> None:
        """Empty dataset list produces valid manifest with empty datasets map."""
        result = build_manifest([], "0.1.0")

        assert result["version"] == "1"
        assert result["publisher_version"] == "0.1.0"
        assert result["datasets"] == {}

    def test_combined_dataset_has_null_boundary_type(self) -> None:
        """Combined all-boundaries entry has null boundary_type and empty filters."""
        ds = _make_dataset_entry("all-boundaries", boundary_type=None)

        result = build_manifest([ds], "0.1.0")

        entry = result["datasets"]["all-boundaries"]
        assert entry["boundary_type"] is None
        assert entry["filters"] == {}
