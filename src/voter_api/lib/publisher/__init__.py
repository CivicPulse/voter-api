"""Publisher library — public API for static dataset publishing.

Provides GeoJSON generation, S3/R2 storage operations, and manifest management
for publishing boundary datasets to object storage.
"""

from voter_api.lib.publisher.generator import generate_boundary_geojson
from voter_api.lib.publisher.manifest import ManifestCache, build_manifest, get_redirect_url
from voter_api.lib.publisher.storage import (
    create_r2_client,
    fetch_manifest,
    upload_file,
    upload_manifest,
    validate_config,
)
from voter_api.lib.publisher.types import DatasetEntry, ManifestData, PublishResult

__all__ = [
    "DatasetEntry",
    "ManifestCache",
    "ManifestData",
    "PublishResult",
    "build_manifest",
    "create_r2_client",
    "fetch_manifest",
    "generate_boundary_geojson",
    "get_redirect_url",
    "upload_file",
    "upload_manifest",
    "validate_config",
]
