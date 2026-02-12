"""Boundary API endpoints for querying and spatial operations."""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, RedirectResponse
from geoalchemy2.shape import to_shape
from loguru import logger
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.config import get_settings
from voter_api.core.dependencies import get_async_session
from voter_api.lib.publisher.manifest import ManifestCache, get_redirect_url
from voter_api.lib.publisher.storage import fetch_manifest
from voter_api.schemas.boundary import (
    BoundaryDetailResponse,
    BoundaryFeatureCollection,
    BoundaryGeoJSONFeature,
    BoundarySummaryResponse,
    BoundaryTypesResponse,
    PaginatedBoundaryResponse,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.services.boundary_service import (
    find_containing_boundaries,
    get_boundary,
    list_boundaries,
    list_boundary_types,
)
from voter_api.services.county_metadata_service import get_county_metadata_by_geoid

# Module-level manifest cache singleton
_manifest_cache: ManifestCache | None = None


def _get_manifest_cache() -> ManifestCache:
    """Get or create the module-level manifest cache singleton."""
    global _manifest_cache  # noqa: PLW0603
    if _manifest_cache is None:
        settings = get_settings()
        _manifest_cache = ManifestCache(ttl_seconds=settings.r2_manifest_ttl)
    return _manifest_cache


async def _try_redirect(
    settings: object,
    boundary_type: str | None,
    county: str | None,
    source: str | None,
) -> str | None:
    """Attempt to resolve a redirect URL from the manifest cache.

    Refreshes the manifest from R2 if the cache is stale, using
    stale-while-revalidate semantics (serves cached data on refresh failure).

    Returns:
        Redirect URL string, or None if fallback to DB is needed.
    """
    from voter_api.lib.publisher.storage import create_r2_client

    cache = _get_manifest_cache()

    if cache.is_stale():
        try:
            client = create_r2_client(
                settings.r2_account_id,
                settings.r2_access_key_id,
                settings.r2_secret_access_key,
            )
            manifest_key = f"{settings.r2_prefix}manifest.json".lstrip("/")
            manifest = await asyncio.to_thread(fetch_manifest, client, settings.r2_bucket, manifest_key)
            if manifest is not None:
                cache.set(manifest)
        except Exception:
            logger.warning("Failed to refresh manifest from R2, using cached data")

    cached = cache.get_data_unchecked() if cache.is_stale() else cache.get()
    return get_redirect_url(cached, boundary_type, county, source)


boundaries_router = APIRouter(prefix="/boundaries", tags=["boundaries"])


@boundaries_router.get(
    "",
    response_model=PaginatedBoundaryResponse,
)
async def list_all_boundaries(
    boundary_type: str | None = Query(None),
    county: str | None = Query(None),
    source: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedBoundaryResponse:
    """List boundaries with optional filters.

    No authentication required. Boundary data is public.
    """
    boundaries, total = await list_boundaries(
        session,
        boundary_type=boundary_type,
        county=county,
        source=source,
        page=page,
        page_size=page_size,
    )
    return PaginatedBoundaryResponse(
        items=[BoundarySummaryResponse.model_validate(b) for b in boundaries],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@boundaries_router.get(
    "/containing-point",
    response_model=list[BoundarySummaryResponse],
)
async def containing_point(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    boundary_type: str | None = Query(None),
    county: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> list[BoundarySummaryResponse]:
    """Find all boundaries containing a given point.

    No authentication required. Boundary data is public.
    """
    boundaries = await find_containing_boundaries(session, latitude, longitude, boundary_type, county=county)
    return [BoundarySummaryResponse.model_validate(b) for b in boundaries]


@boundaries_router.get(
    "/geojson",
    response_model=BoundaryFeatureCollection,
)
async def get_boundaries_geojson(
    boundary_type: str | None = Query(None),
    county: str | None = Query(None),
    source: str | None = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse | RedirectResponse:
    """Return boundaries as a public GeoJSON FeatureCollection.

    When static datasets are published to R2 and a matching dataset exists,
    returns HTTP 302 redirect. Otherwise serves from database.
    No authentication required. Intended for consumption by map libraries
    (Leaflet, Mapbox GL, OpenLayers).
    """
    # Check for R2 redirect
    settings = get_settings()
    if settings.r2_enabled:
        redirect_url = await _try_redirect(settings, boundary_type, county, source)
        if redirect_url:
            return RedirectResponse(url=redirect_url, status_code=302)

    boundaries, _ = await list_boundaries(
        session,
        boundary_type=boundary_type,
        county=county,
        source=source,
        page=1,
        page_size=10_000,
    )

    features: list[dict] = []
    for b in boundaries:
        geom_shape = to_shape(b.geometry)
        feature = BoundaryGeoJSONFeature(
            id=str(b.id),
            geometry=mapping(geom_shape),
            properties={
                "name": b.name,
                "boundary_type": b.boundary_type,
                "boundary_identifier": b.boundary_identifier,
                "source": b.source,
                "county": b.county,
            },
        )
        features.append(feature.model_dump())

    collection = BoundaryFeatureCollection(features=features)
    return JSONResponse(
        content=collection.model_dump(),
        media_type="application/geo+json",
    )


@boundaries_router.get(
    "/types",
    response_model=BoundaryTypesResponse,
)
async def get_boundary_types(
    session: AsyncSession = Depends(get_async_session),
) -> BoundaryTypesResponse:
    """List distinct boundary types, sorted alphabetically.

    No authentication required. Boundary data is public.
    """
    types = await list_boundary_types(session)
    return BoundaryTypesResponse(types=types)


@boundaries_router.get(
    "/{boundary_id}",
    response_model=BoundaryDetailResponse,
)
async def get_boundary_detail(
    boundary_id: uuid.UUID,
    include_geometry: bool = Query(True),
    session: AsyncSession = Depends(get_async_session),
) -> BoundaryDetailResponse:
    """Get boundary details with optional geometry.

    No authentication required. Boundary data is public.
    """
    boundary = await get_boundary(session, boundary_id)
    if boundary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Boundary not found")

    response_data = {
        "id": boundary.id,
        "name": boundary.name,
        "boundary_type": boundary.boundary_type,
        "boundary_identifier": boundary.boundary_identifier,
        "source": boundary.source,
        "county": boundary.county,
        "effective_date": boundary.effective_date,
        "created_at": boundary.created_at,
        "properties": boundary.properties,
    }

    if include_geometry and boundary.geometry:
        geom_shape = to_shape(boundary.geometry)
        response_data["geometry"] = mapping(geom_shape)

    # Include county metadata for county boundaries
    if boundary.boundary_type == "county":
        metadata = await get_county_metadata_by_geoid(session, boundary.boundary_identifier)
        if metadata:
            from voter_api.schemas.county_metadata import CountyMetadataResponse

            response_data["county_metadata"] = CountyMetadataResponse.model_validate(metadata)

    return BoundaryDetailResponse(**response_data)
