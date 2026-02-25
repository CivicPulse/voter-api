"""Voter API endpoints for search, detail, and geocoded location management."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.lib.normalize import normalize_registration_number
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.geocoding import GeocodedLocationResponse, ManualGeocodingRequest
from voter_api.schemas.voter import (
    DistrictCheckResponse,
    OfficialLocationResponse,
    PaginatedVoterResponse,
    SetOfficialLocationRequest,
    VoterDetailResponse,
    VoterFilterOptions,
    VoterSummaryResponse,
)
from voter_api.services.geocoding_service import (
    add_manual_location,
    clear_official_location_override,
    get_voter_locations,
    set_official_location_override,
    set_primary_location,
)
from voter_api.services.voter_history_service import get_participation_summary
from voter_api.services.voter_service import (
    build_voter_detail_dict,
    check_voter_districts,
    get_voter_detail,
    get_voter_filter_options,
    search_voters,
)

voters_router = APIRouter(prefix="/voters", tags=["voters"])

VOTER_NOT_FOUND = "Voter not found"


@voters_router.get(
    "",
    response_model=PaginatedVoterResponse,
)
async def search_voters_endpoint(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(None, description="Combined name search across first, last, and middle name", max_length=500),
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
    county_commission_district: str | None = Query(None),
    school_board_district: str | None = Query(None),
    present_in_latest_import: bool | None = Query(None),
    has_district_mismatch: bool | None = Query(None, description="Filter by district mismatch status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PaginatedVoterResponse:
    """Search and list voters with multiple filter parameters."""
    if voter_registration_number:
        voter_registration_number = normalize_registration_number(voter_registration_number)
    voters, total = await search_voters(
        session,
        q=q,
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
        county_commission_district=county_commission_district,
        school_board_district=school_board_district,
        present_in_latest_import=present_in_latest_import,
        has_district_mismatch=has_district_mismatch,
        page=page,
        page_size=page_size,
    )
    return PaginatedVoterResponse(
        items=[VoterSummaryResponse.model_validate(v) for v in voters],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@voters_router.get(
    "/filters",
    response_model=VoterFilterOptions,
    response_model_exclude_none=True,
)
async def get_filter_options(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
    county: str | None = Query(None, description="County name to scope county-level filter options"),
    county_precinct: str | None = Query(None, description="Precinct to narrow other county-scoped options"),
    county_commission_district: str | None = Query(
        None, description="Commission district to narrow other county-scoped options"
    ),
    school_board_district: str | None = Query(
        None, description="School board district to narrow other county-scoped options"
    ),
) -> VoterFilterOptions:
    """Return distinct values for voter search filter dropdowns.

    Queries the database for all non-null distinct values currently present in
    the voters table.  Use this endpoint to populate dropdown/select components
    in search UIs.

    Cascading filters: when county-scoped params are provided alongside
    ``county``, each narrows the *other* county-scoped lists but not its own,
    enabling dependent dropdown UIs.

    Args:
        county: County name used to scope county-level filter options.
        county_precinct: Precinct value that narrows other county-scoped lists.
        county_commission_district: Commission district that narrows other
            county-scoped lists.
        school_board_district: School board district that narrows other
            county-scoped lists.
        session: Async database session.
        _current_user: Authenticated user dependency.

    Returns:
        VoterFilterOptions with base filters always present.  County-scoped
        fields are included only when ``county`` is provided.
    """
    options = await get_voter_filter_options(
        session,
        county=county,
        county_precinct=county_precinct,
        county_commission_district=county_commission_district,
        school_board_district=school_board_district,
    )
    return VoterFilterOptions(**options)


@voters_router.get(
    "/{voter_id}",
    response_model=VoterDetailResponse,
)
async def get_voter(
    voter_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> VoterDetailResponse:
    """Get full voter details by ID."""
    voter = await get_voter_detail(session, voter_id)
    if voter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=VOTER_NOT_FOUND)
    detail_dict = build_voter_detail_dict(voter)
    summary = await get_participation_summary(session, voter.voter_registration_number)
    detail_dict["participation_summary"] = summary
    return VoterDetailResponse(**detail_dict)


@voters_router.get("/{voter_id}/district-check", response_model=DistrictCheckResponse)
async def check_voter_district_assignments(
    voter_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> DistrictCheckResponse:
    """Check a voter's registered districts against their geocoded location.

    Performs real-time point-in-polygon analysis and returns registered vs
    geographic districts with mismatch classification.
    """
    result = await check_voter_districts(session, voter_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=VOTER_NOT_FOUND)
    return DistrictCheckResponse(**result)


@voters_router.get(
    "/{voter_id}/geocoded-locations",
    response_model=list[GeocodedLocationResponse],
)
async def list_voter_locations(
    voter_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
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
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
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
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> GeocodedLocationResponse:
    """Set a geocoded location as primary for a voter (admin only)."""
    location = await set_primary_location(session, voter_id, location_id)
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geocoded location not found",
        )
    return GeocodedLocationResponse.model_validate(location)


@voters_router.put(
    "/{voter_id}/official-location",
    response_model=OfficialLocationResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def set_voter_official_location(
    voter_id: uuid.UUID,
    request: SetOfficialLocationRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> OfficialLocationResponse:
    """Set an admin override for a voter's official location (admin only)."""
    try:
        voter = await set_official_location_override(session, voter_id, request.latitude, request.longitude)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=VOTER_NOT_FOUND) from err
    return OfficialLocationResponse(
        latitude=voter.official_latitude,
        longitude=voter.official_longitude,
        source=voter.official_source,
        is_override=voter.official_is_override,
    )


@voters_router.delete(
    "/{voter_id}/official-location/override",
    response_model=OfficialLocationResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def clear_voter_official_location_override(
    voter_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(get_current_user)],
) -> OfficialLocationResponse:
    """Clear an admin override and revert to the best geocoded location (admin only)."""
    try:
        voter = await clear_official_location_override(session, voter_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=VOTER_NOT_FOUND) from err
    return OfficialLocationResponse(
        latitude=voter.official_latitude,
        longitude=voter.official_longitude,
        source=voter.official_source,
        is_override=voter.official_is_override,
    )
