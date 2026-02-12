"""Boundary API endpoints for querying and spatial operations."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session
from voter_api.schemas.boundary import (
    BoundaryDetailResponse,
    BoundaryFeatureCollection,
    BoundaryGeoJSONFeature,
    BoundarySummaryResponse,
    PaginatedBoundaryResponse,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.services.boundary_service import (
    find_containing_boundaries,
    get_boundary,
    list_boundaries,
)

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
) -> JSONResponse:
    """Return boundaries as a public GeoJSON FeatureCollection.

    No authentication required. Intended for consumption by map libraries
    (Leaflet, Mapbox GL, OpenLayers).
    """
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

    return BoundaryDetailResponse(**response_data)
