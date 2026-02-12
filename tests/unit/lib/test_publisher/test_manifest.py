"""Unit tests for publisher manifest builder, cache, and redirect URL logic."""

import time
from datetime import UTC, datetime

from voter_api.lib.publisher.manifest import ManifestCache, build_manifest, get_redirect_url
from voter_api.lib.publisher.types import DatasetEntry, ManifestData


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


def _make_manifest_data(
    datasets: dict[str, DatasetEntry] | None = None,
) -> ManifestData:
    """Create a test ManifestData."""
    if datasets is None:
        datasets = {
            "congressional": _make_dataset_entry("congressional"),
            "all-boundaries": _make_dataset_entry("all-boundaries", boundary_type=None),
        }
    return ManifestData(
        version="1",
        published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
        publisher_version="0.1.0",
        datasets=datasets,
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


class TestManifestCache:
    """Tests for ManifestCache."""

    def test_get_returns_none_when_empty(self) -> None:
        """Cache get() returns None when no data has been set."""
        cache = ManifestCache(ttl_seconds=300)
        assert cache.get() is None

    def test_get_returns_data_within_ttl(self) -> None:
        """Cache get() returns data when within TTL."""
        cache = ManifestCache(ttl_seconds=300)
        manifest = _make_manifest_data()
        cache.set(manifest)

        result = cache.get()

        assert result is not None
        assert result.version == "1"

    def test_is_stale_returns_true_after_ttl_expires(self) -> None:
        """Cache is_stale() returns True after TTL expires."""
        cache = ManifestCache(ttl_seconds=0)  # Immediate expiry
        manifest = _make_manifest_data()
        cache.set(manifest)
        time.sleep(0.01)

        assert cache.is_stale() is True

    def test_is_stale_returns_true_when_empty(self) -> None:
        """Cache is_stale() returns True when empty."""
        cache = ManifestCache(ttl_seconds=300)
        assert cache.is_stale() is True

    def test_invalidate_clears_cache(self) -> None:
        """invalidate() clears cached data."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())

        cache.invalidate()

        assert cache.get() is None
        assert cache.is_stale() is True

    def test_get_data_unchecked_returns_stale_data(self) -> None:
        """get_data_unchecked() returns data regardless of TTL."""
        cache = ManifestCache(ttl_seconds=0)
        manifest = _make_manifest_data()
        cache.set(manifest)
        time.sleep(0.01)

        assert cache.get() is None  # Expired
        assert cache.get_data_unchecked() is not None  # Still accessible


class TestGetRedirectUrl:
    """Tests for get_redirect_url."""

    def test_returns_all_boundaries_url_for_no_filters(self) -> None:
        """No filters returns all-boundaries URL."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, None, None, None)

        assert url == "https://geo.example.com/boundaries/all-boundaries.geojson"

    def test_returns_type_specific_url_for_boundary_type(self) -> None:
        """boundary_type filter returns type-specific URL."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, "congressional", None, None)

        assert url == "https://geo.example.com/boundaries/congressional.geojson"

    def test_returns_none_for_county_filter(self) -> None:
        """county filter always returns None (fallback to DB)."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, None, "Fulton", None)

        assert url is None

    def test_returns_none_for_source_filter(self) -> None:
        """source filter always returns None (fallback to DB)."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, None, None, "state")

        assert url is None

    def test_returns_none_for_mixed_filters(self) -> None:
        """boundary_type + county returns None (county forces fallback)."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, "congressional", "Fulton", None)

        assert url is None

    def test_returns_none_when_no_matching_dataset(self) -> None:
        """Returns None when boundary_type not in manifest."""
        manifest = _make_manifest_data()

        url = get_redirect_url(manifest, "nonexistent_type", None, None)

        assert url is None

    def test_returns_none_when_manifest_is_none(self) -> None:
        """Returns None when manifest is None."""
        url = get_redirect_url(None, None, None, None)

        assert url is None

    def test_returns_none_when_manifest_has_no_datasets(self) -> None:
        """Returns None when manifest has empty datasets."""
        manifest = _make_manifest_data(datasets={})

        url = get_redirect_url(manifest, None, None, None)

        assert url is None
