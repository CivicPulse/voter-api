"""Publish service — orchestrates boundary dataset generation and upload to R2.

Queries boundaries from the database, generates GeoJSON files, uploads them
to object storage, and produces a manifest.
"""

import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import to_shape
from loguru import logger
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.publisher.generator import generate_boundary_geojson
from voter_api.lib.publisher.manifest import build_manifest
from voter_api.lib.publisher.storage import upload_file, upload_manifest
from voter_api.lib.publisher.types import DatasetEntry, PublishResult
from voter_api.models.boundary import Boundary
from voter_api.services.boundary_service import list_boundaries


def boundary_to_feature_dict(boundary: Boundary) -> dict[str, Any]:
    """Convert a Boundary ORM model to a GeoJSON feature dict.

    Matches the exact feature structure of the existing
    GET /api/v1/boundaries/geojson endpoint.

    Args:
        boundary: Boundary ORM instance with loaded geometry.

    Returns:
        GeoJSON Feature dict with id, geometry, and properties.
    """
    geom_shape = to_shape(boundary.geometry)
    return {
        "type": "Feature",
        "id": str(boundary.id),
        "geometry": mapping(geom_shape),
        "properties": {
            "name": boundary.name,
            "boundary_type": boundary.boundary_type,
            "boundary_identifier": boundary.boundary_identifier,
            "source": boundary.source,
            "county": boundary.county,
        },
    }


async def publish_datasets(
    session: AsyncSession,
    client: Any,
    bucket: str,
    public_url: str,
    prefix: str,
    *,
    publisher_version: str = "",
    boundary_type: str | None = None,
    county: str | None = None,
    source: str | None = None,
) -> PublishResult:
    """Generate and upload boundary GeoJSON datasets to R2.

    Queries all boundaries from the database, groups by boundary_type,
    generates per-type GeoJSON files plus a combined all-boundaries file,
    uploads them to R2, and creates a manifest.

    Args:
        session: Database session for querying boundaries.
        client: boto3 S3 client.
        bucket: R2 bucket name.
        public_url: Public URL prefix for constructing dataset URLs.
        prefix: Key prefix within the bucket.
        publisher_version: Version string for the manifest.
        boundary_type: Optional filter to publish only this boundary type.
        county: Optional filter — unused for US1 (added for US2 compatibility).
        source: Optional filter — unused for US1 (added for US2 compatibility).

    Returns:
        PublishResult with details of all uploaded datasets.
    """
    start_time = time.monotonic()

    # Query all boundaries
    boundaries, total = await list_boundaries(
        session,
        boundary_type=boundary_type,
        county=county,
        source=source,
        page=1,
        page_size=100_000,
    )

    if not boundaries:
        logger.info("No boundaries found — nothing to publish")
        manifest_key = f"{prefix}manifest.json".lstrip("/")
        return PublishResult(
            datasets=[],
            manifest_key=manifest_key,
            total_records=0,
            total_size_bytes=0,
            duration_seconds=time.monotonic() - start_time,
        )

    # Convert to feature dicts
    features_by_type: dict[str, list[dict[str, Any]]] = {}
    all_features: list[dict[str, Any]] = []

    for b in boundaries:
        feature = boundary_to_feature_dict(b)
        all_features.append(feature)
        bt = b.boundary_type
        if bt not in features_by_type:
            features_by_type[bt] = []
        features_by_type[bt].append(feature)

    logger.info(
        "Found {} boundaries across {} types",
        len(all_features),
        len(features_by_type),
    )

    datasets: list[DatasetEntry] = []
    now = datetime.now(tz=UTC)
    public_url = public_url.rstrip("/")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Generate and upload per-type files
        for bt, features in sorted(features_by_type.items()):
            file_name = f"{bt}.geojson"
            local_path = tmp_path / file_name
            record_count = generate_boundary_geojson(features, local_path)

            key = f"{prefix}boundaries/{file_name}".lstrip("/")
            file_size = upload_file(client, bucket, key, local_path)

            datasets.append(
                DatasetEntry(
                    name=bt,
                    key=key,
                    public_url=f"{public_url}/{key}",
                    content_type="application/geo+json",
                    record_count=record_count,
                    file_size_bytes=file_size,
                    boundary_type=bt,
                    filters={"boundary_type": bt},
                    published_at=now,
                )
            )
            logger.info("Published {}: {} features, {} bytes", bt, record_count, file_size)

        # Generate and upload combined all-boundaries file
        combined_name = "all-boundaries.geojson"
        combined_path = tmp_path / combined_name
        combined_count = generate_boundary_geojson(all_features, combined_path)

        combined_key = f"{prefix}boundaries/{combined_name}".lstrip("/")
        combined_size = upload_file(client, bucket, combined_key, combined_path)

        datasets.append(
            DatasetEntry(
                name="all-boundaries",
                key=combined_key,
                public_url=f"{public_url}/{combined_key}",
                content_type="application/geo+json",
                record_count=combined_count,
                file_size_bytes=combined_size,
                boundary_type=None,
                filters={},
                published_at=now,
            )
        )
        logger.info(
            "Published all-boundaries: {} features, {} bytes",
            combined_count,
            combined_size,
        )

    # Build and upload manifest (last — acts as atomic "commit")
    manifest_key = f"{prefix}manifest.json".lstrip("/")
    manifest_data = build_manifest(datasets, publisher_version)
    upload_manifest(client, bucket, manifest_key, manifest_data)

    duration = time.monotonic() - start_time
    total_records = sum(ds.record_count for ds in datasets)
    total_size = sum(ds.file_size_bytes for ds in datasets)

    logger.info(
        "Publish complete: {} datasets, {} records, {} bytes in {:.1f}s",
        len(datasets),
        total_records,
        total_size,
        duration,
    )

    return PublishResult(
        datasets=datasets,
        manifest_key=manifest_key,
        total_records=total_records,
        total_size_bytes=total_size,
        duration_seconds=duration,
    )
