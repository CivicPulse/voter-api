"""Voter API endpoints for search, detail, and geocoded location management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.geocoding import GeocodedLocationResponse, ManualGeocodingRequest
from voter_api.schemas.voter import (
    PaginatedVoterResponse,
    VoterDetailResponse,
    VoterSummaryResponse,
)
from voter_api.services.geocoding_service import (
    add_manual_location,
    get_voter_locations,
    set_primary_location,
)
from voter_api.services.voter_service import (
    build_voter_detail_dict,
    get_voter_detail,
    search_voters,
)

voters_router = APIRouter(prefix="/voters", tags=["voters"])


@voters_router.get(
    "",
    response_model=PaginatedVoterResponse,
)
async def search_voters_endpoint(
    voter_registration_number: str | None = Query(None),
    first_name: str | None = Query(None),
    last_name: str | None = Query(None),
    county: str | None = Query(None),
    residence_city: str | None = Query(None),
    residence_zipcode: str | None = Query(None),
    voter_status: str | None = Query(None, alias="status"),
    congressional_district: str | None = Query(None),
    state_senate_district: str | None = Query(None),
    state_house_district: str | None = Query(None),
    county_precinct: str | None = Query(None),
    present_in_latest_import: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
) -> PaginatedVoterResponse:
    """Search and list voters with multiple filter parameters."""
    voters, total = await search_voters(
        session,
        voter_registration_number=voter_registration_number,
        first_name=first_name,
        last_name=last_name,
        county=county,
        residence_city=residence_city,
        residence_zipcode=residence_zipcode,
        status=voter_status,
        congressional_district=congressional_district,
        state_senate_district=state_senate_district,
        state_house_district=state_house_district,
        county_precinct=county_precinct,
        present_in_latest_import=present_in_latest_import,
        page=page,
        page_size=page_size,
    )
    return PaginatedVoterResponse(
        items=[VoterSummaryResponse.model_validate(v) for v in voters],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@voters_router.get(
    "/{voter_id}",
    response_model=VoterDetailResponse,
)
async def get_voter(
    voter_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
) -> VoterDetailResponse:
    """Get full voter details by ID."""
    voter = await get_voter_detail(session, voter_id)
    if voter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voter not found")
    detail_dict = build_voter_detail_dict(voter)
    return VoterDetailResponse(**detail_dict)


@voters_router.get(
    "/{voter_id}/geocoded-locations",
    response_model=list[GeocodedLocationResponse],
)
async def list_voter_locations(
    voter_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
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
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
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
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
) -> GeocodedLocationResponse:
    """Set a geocoded location as primary for a voter (admin only)."""
    location = await set_primary_location(session, voter_id, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geocoded location not found",
        )
    return GeocodedLocationResponse.model_validate(location)
