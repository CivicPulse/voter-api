"""Voter API endpoints for geocoded location management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.schemas.geocoding import GeocodedLocationResponse, ManualGeocodingRequest
from voter_api.services.geocoding_service import (
    add_manual_location,
    get_voter_locations,
    set_primary_location,
)

voters_router = APIRouter(prefix="/voters", tags=["voters"])


@voters_router.get(
    "/{voter_id}/geocoded-locations",
    response_model=list[GeocodedLocationResponse],
)
async def list_voter_locations(
    voter_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
) -> list[GeocodedLocationResponse]:
    """List all geocoded locations for a voter."""
    locations = await get_voter_locations(session, voter_id)
    return [GeocodedLocationResponse.model_validate(loc) for loc in locations]


@voters_router.post(
    "/{voter_id}/geocoded-locations/manual",
    response_model=GeocodedLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_manual_geocoded_location(
    voter_id: uuid.UUID,
    request: ManualGeocodingRequest,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
) -> GeocodedLocationResponse:
    """Add a manual geocoded location for a voter."""
    location = await add_manual_location(
        session,
        voter_id=voter_id,
        latitude=request.latitude,
        longitude=request.longitude,
        source_type=request.source_type,
        set_as_primary=request.set_as_primary,
    )
    return GeocodedLocationResponse.model_validate(location)


@voters_router.put(
    "/{voter_id}/geocoded-locations/{location_id}/set-primary",
    response_model=GeocodedLocationResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def set_primary_geocoded_location(
    voter_id: uuid.UUID,
    location_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: dict = Depends(get_current_user),  # noqa: B008
) -> GeocodedLocationResponse:
    """Set a geocoded location as primary for a voter (admin only)."""
    location = await set_primary_location(session, voter_id, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geocoded location not found",
        )
    return GeocodedLocationResponse.model_validate(location)
