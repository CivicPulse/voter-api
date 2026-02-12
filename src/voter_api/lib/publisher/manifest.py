"""Manifest generation, caching, and redirect URL resolution.

Builds manifest.json dicts from dataset entries, provides a TTL-based
in-memory cache for API-side manifest lookups, and resolves redirect
URLs from cached manifest data.
"""

import threading
import time
from datetime import UTC, datetime
from typing import Any

from voter_api.lib.publisher.types import DatasetEntry, ManifestData


def build_manifest(datasets: list[DatasetEntry], publisher_version: str) -> dict[str, Any]:
    """Construct a manifest.json dict from dataset entries.

    Args:
        datasets: List of DatasetEntry objects to include in the manifest.
        publisher_version: Version string of the publisher library.

    Returns:
        Manifest dict ready for JSON serialization.
    """
    datasets_map: dict[str, dict[str, Any]] = {}
    for ds in datasets:
        datasets_map[ds.name] = {
            "key": ds.key,
            "public_url": ds.public_url,
            "content_type": ds.content_type,
            "record_count": ds.record_count,
            "file_size_bytes": ds.file_size_bytes,
            "boundary_type": ds.boundary_type,
            "filters": ds.filters,
            "published_at": ds.published_at.isoformat(),
        }

    return {
        "version": "1",
        "published_at": datetime.now(tz=UTC).isoformat(),
        "publisher_version": publisher_version,
        "datasets": datasets_map,
    }


class ManifestCache:
    """TTL-based in-memory cache for manifest data.

    Thread-safe cache that stores a single ManifestData instance with
    configurable TTL-based expiration. Used by the API to avoid fetching
    the manifest from R2 on every request.

    Args:
        ttl_seconds: Cache time-to-live in seconds.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._data: ManifestData | None = None
        self._cached_at: float | None = None
        self._lock = threading.Lock()

    def get(self) -> ManifestData | None:
        """Return cached manifest if within TTL, else None.

        Returns:
            Cached ManifestData if valid, None if cache is empty or expired.
        """
        with self._lock:
            if self._data is None or self._cached_at is None:
                return None
            if self.is_stale():
                return None
            return self._data

    def set(self, data: ManifestData) -> None:
        """Update the cache with new manifest data.

        Args:
            data: ManifestData to cache.
        """
        with self._lock:
            self._data = data
            self._cached_at = time.monotonic()

    def invalidate(self) -> None:
        """Clear the cache."""
        with self._lock:
            self._data = None
            self._cached_at = None

    def is_stale(self) -> bool:
        """Check if the cache TTL has expired.

        Returns:
            True if cache is empty or TTL has expired.
        """
        if self._cached_at is None:
            return True
        return (time.monotonic() - self._cached_at) >= self._ttl_seconds

    @property
    def cached_at_datetime(self) -> datetime | None:
        """Return the cache timestamp as a datetime, or None."""
        if self._cached_at is None:
            return None
        # Convert monotonic offset to approximate wall-clock time
        elapsed = time.monotonic() - self._cached_at
        return datetime.now(tz=UTC) - __import__("datetime").timedelta(seconds=elapsed)

    def get_data_unchecked(self) -> ManifestData | None:
        """Return cached data regardless of TTL (for stale-while-revalidate).

        Returns:
            Cached ManifestData or None if never set.
        """
        with self._lock:
            return self._data


def get_redirect_url(
    manifest: ManifestData | None,
    boundary_type: str | None,
    county: str | None,
    source: str | None,
) -> str | None:
    """Determine redirect URL from manifest based on query parameters.

    Follows the redirect lookup rules from data-model.md:
    1. No filters -> datasets["all-boundaries"].public_url
    2. boundary_type only -> datasets[boundary_type].public_url if exists
    3. Any county or source filter -> None (always fall back to DB)
    4. Manifest empty/None -> None

    Args:
        manifest: Cached manifest data, or None.
        boundary_type: Boundary type filter from query params.
        county: County filter from query params.
        source: Source filter from query params.

    Returns:
        Public URL to redirect to, or None if fallback to DB is needed.
    """
    if manifest is None:
        return None

    if not manifest.datasets:
        return None

    # Any county or source filter always falls back to DB
    if county or source:
        return None

    # No filters -> combined file
    if boundary_type is None:
        entry = manifest.datasets.get("all-boundaries")
        return entry.public_url if entry else None

    # boundary_type filter -> type-specific file
    entry = manifest.datasets.get(boundary_type)
    return entry.public_url if entry else None
