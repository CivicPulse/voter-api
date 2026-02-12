"""Publish service — orchestrates boundary dataset generation and upload to R2.

Queries boundaries from the database, generates GeoJSON files, uploads them
to object storage, and produces a manifest.
"""

import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from geoalchemy2.shape import to_shape
from loguru import logger
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.publisher.generator import generate_boundary_geojson
from voter_api.lib.publisher.manifest import build_manifest
from voter_api.lib.publisher.storage import fetch_manifest, upload_file, upload_manifest
from voter_api.lib.publisher.types import DatasetEntry, PublishResult
from voter_api.models.boundary import Boundary
from voter_api.services.boundary_service import list_boundaries
from voter_api.services.precinct_metadata_service import get_precinct_metadata_batch


def boundary_to_feature_dict(
    boundary: Boundary,
    precinct_metadata_map: dict[uuid.UUID, Any] | None = None,
) -> dict[str, Any]:
    """Convert a Boundary ORM model to a GeoJSON feature dict.

    Matches the exact feature structure of the existing
    GET /api/v1/boundaries/geojson endpoint.

    Args:
        boundary: Boundary ORM instance with loaded geometry.
        precinct_metadata_map: Optional dict mapping boundary_id to
            PrecinctMetadata records for enriching county_precinct features.

    Returns:
        GeoJSON Feature dict with id, geometry, and properties.
    """
    geom_shape = to_shape(boundary.geometry)
    properties: dict[str, Any] = {
        "name": boundary.name,
        "boundary_type": boundary.boundary_type,
        "boundary_identifier": boundary.boundary_identifier,
        "source": boundary.source,
        "county": boundary.county,
    }

    if boundary.boundary_type == "county_precinct" and precinct_metadata_map and boundary.id in precinct_metadata_map:
        meta = precinct_metadata_map[boundary.id]
        properties.update(
            {
                "precinct_name": meta.precinct_name,
                "precinct_id": meta.precinct_id,
                "precinct_fips": meta.fips,
                "precinct_fips_county": meta.fips_county,
                "precinct_county_name": meta.county_name,
                "precinct_county_number": meta.county_number,
                "precinct_sos_district_id": meta.sos_district_id,
                "precinct_sos_id": meta.sos_id,
                "precinct_area": float(meta.area) if meta.area is not None else None,
            }
        )

    return {
        "type": "Feature",
        "id": str(boundary.id),
        "geometry": mapping(geom_shape),
        "properties": properties,
    }


async def _get_types_to_regenerate(
    session: AsyncSession,
    *,
    county: str | None = None,
    source: str | None = None,
) -> list[str]:
    """Identify which boundary types need regeneration for county/source filters.

    When county or source is specified, queries the DB to find which
    boundary types contain matching boundaries.

    Args:
        session: Database session.
        county: County name to filter by.
        source: Source to filter by.

    Returns:
        List of distinct boundary type strings.
    """

    query = select(Boundary.boundary_type).distinct()
    if county:
        query = query.where(Boundary.county == county)
    if source:
        query = query.where(Boundary.source == source)

    result = await session.execute(query)
    return [row[0] for row in result.all()]


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

    Queries boundaries from the database, groups by boundary_type,
    generates GeoJSON files, uploads them to R2, and creates a manifest.

    When filters are active:
    - boundary_type: regenerates only that type's file
    - county/source: identifies which types contain matching boundaries,
      then regenerates those types' files (each file contains ALL boundaries
      of its type, not just the matching ones)
    - Filtered publishes skip the combined all-boundaries file
    - Filtered publishes merge into the existing manifest

    Args:
        session: Database session for querying boundaries.
        client: boto3 S3 client.
        bucket: R2 bucket name.
        public_url: Public URL prefix for constructing dataset URLs.
        prefix: Key prefix within the bucket.
        publisher_version: Version string for the manifest.
        boundary_type: Optional filter to publish only this boundary type.
        county: Optional scope — regenerate only types containing this county.
        source: Optional scope — regenerate only types containing this source.

    Returns:
        PublishResult with details of all uploaded datasets.
    """
    start_time = time.monotonic()
    is_filtered = any([boundary_type, county, source])

    # Determine which types to regenerate
    if boundary_type:
        types_to_regenerate = [boundary_type]
    elif county or source:
        types_to_regenerate = await _get_types_to_regenerate(session, county=county, source=source)
        if not types_to_regenerate:
            logger.info("No boundary types match the specified filters — nothing to publish")
            manifest_key = f"{prefix}manifest.json".lstrip("/")
            return PublishResult(
                datasets=[],
                manifest_key=manifest_key,
                total_records=0,
                total_size_bytes=0,
                duration_seconds=time.monotonic() - start_time,
            )
    else:
        types_to_regenerate = None  # All types

    # For each type to regenerate, query ALL boundaries of that type
    all_boundaries: list[Boundary] = []

    if types_to_regenerate is not None:
        # Filtered: query each type separately (full data for each type)
        for bt in types_to_regenerate:
            boundaries, _ = await list_boundaries(session, boundary_type=bt, page=1, page_size=100_000)
            all_boundaries.extend(boundaries)
    else:
        # Unfiltered: query all
        boundaries, _ = await list_boundaries(session, page=1, page_size=100_000)
        all_boundaries.extend(boundaries)

    # Batch-load precinct metadata for county_precinct boundaries
    precinct_ids = [b.id for b in all_boundaries if b.boundary_type == "county_precinct"]
    precinct_meta_map = await get_precinct_metadata_batch(session, precinct_ids) if precinct_ids else {}

    # Generate features with enriched metadata
    features_by_type: dict[str, list[dict[str, Any]]] = {}
    all_features: list[dict[str, Any]] = []

    for b in all_boundaries:
        feature = boundary_to_feature_dict(b, precinct_metadata_map=precinct_meta_map)
        all_features.append(feature)
        bt = b.boundary_type
        if bt not in features_by_type:
            features_by_type[bt] = []
        features_by_type[bt].append(feature)

    if not features_by_type:
        logger.info("No boundaries found — nothing to publish")
        manifest_key = f"{prefix}manifest.json".lstrip("/")
        return PublishResult(
            datasets=[],
            manifest_key=manifest_key,
            total_records=0,
            total_size_bytes=0,
            duration_seconds=time.monotonic() - start_time,
        )

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

        # Generate combined all-boundaries file (only for unfiltered publishes)
        if not is_filtered:
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

    # Build manifest — merge with existing for filtered publishes
    manifest_key = f"{prefix}manifest.json".lstrip("/")

    if is_filtered:
        # Fetch existing manifest and merge
        existing_manifest = fetch_manifest(client, bucket, manifest_key)
        if existing_manifest:
            # Start with existing datasets, overwrite with new ones
            merged_datasets = list(existing_manifest.datasets.values())
            new_names = {ds.name for ds in datasets}
            merged_datasets = [ds for ds in merged_datasets if ds.name not in new_names]
            merged_datasets.extend(datasets)
            manifest_data = build_manifest(merged_datasets, publisher_version)
        else:
            manifest_data = build_manifest(datasets, publisher_version)
    else:
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
