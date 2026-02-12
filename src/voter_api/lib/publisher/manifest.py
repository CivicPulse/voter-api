"""Manifest generation for static dataset publishing.

Builds manifest.json dicts from dataset entries following the schema
defined in data-model.md.
"""

from datetime import UTC, datetime
from typing import Any

from voter_api.lib.publisher.types import DatasetEntry


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
