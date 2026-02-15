"""Elected officials API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.elected_official import (
    ApproveOfficialRequest,
    ElectedOfficialCreateRequest,
    ElectedOfficialDetailResponse,
    ElectedOfficialSourceResponse,
    ElectedOfficialSummaryResponse,
    ElectedOfficialUpdateRequest,
    PaginatedElectedOfficialResponse,
)
from voter_api.services.elected_official_service import (
    approve_official,
    create_official,
    delete_official,
    get_official,
    get_officials_for_district,
    list_officials,
    list_sources_for_district,
    update_official,
)

elected_officials_router = APIRouter(prefix="/elected-officials", tags=["elected-officials"])


# ---------------------------------------------------------------------------
# Public endpoints (fixed-prefix routes BEFORE parameterized routes)
# ---------------------------------------------------------------------------


@elected_officials_router.get(
    "",
    response_model=PaginatedElectedOfficialResponse,
)
async def list_all_officials(
    boundary_type: str | None = Query(None, description="Filter by boundary type"),
    district_identifier: str | None = Query(None, description="Filter by district identifier"),
    party: str | None = Query(None, description="Filter by party affiliation"),
    official_status: str | None = Query(None, alias="status", description="Filter by approval status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
) -> PaginatedElectedOfficialResponse:
    """List elected officials with optional filters.

    No authentication required. Elected official data is public.
    """
    try:
        officials, total = await list_officials(
            session,
            boundary_type=boundary_type,
            district_identifier=district_identifier,
            party=party,
            status=official_status,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Unexpected error listing officials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error listing elected officials.",
        ) from e
    return PaginatedElectedOfficialResponse(
        items=[ElectedOfficialSummaryResponse.model_validate(o) for o in officials],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        ),
    )


@elected_officials_router.get(
    "/by-district",
    response_model=list[ElectedOfficialDetailResponse],
)
async def officials_by_district(
    boundary_type: str = Query(..., description="Boundary type (e.g. congressional, state_senate)"),
    district_identifier: str = Query(..., description="District identifier"),
    session: AsyncSession = Depends(get_async_session),
) -> list[ElectedOfficialDetailResponse]:
    """Get all elected officials for a specific district.

    No authentication required. Intended for district detail pages.
    """
    try:
        officials = await get_officials_for_district(session, boundary_type, district_identifier)
    except Exception as e:
        logger.error(f"Unexpected error fetching district officials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching district officials.",
        ) from e
    return [ElectedOfficialDetailResponse.model_validate(o) for o in officials]


@elected_officials_router.get(
    "/district/{boundary_type}/{district_identifier}/sources",
    response_model=list[ElectedOfficialSourceResponse],
)
async def get_district_sources(
    boundary_type: str,
    district_identifier: str,
    current_only: bool = Query(True, description="Only return current (latest) source records"),
    session: AsyncSession = Depends(get_async_session),
    _admin: User = Depends(require_role("admin")),
) -> list[ElectedOfficialSourceResponse]:
    """List all source records for a district across all providers.

    Requires admin authentication. Useful for comparing data from
    different sources before approving the canonical record.
    """
    try:
        sources = await list_sources_for_district(
            session, boundary_type, district_identifier, current_only=current_only
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching district sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching district sources.",
        ) from e
    return [ElectedOfficialSourceResponse.model_validate(s) for s in sources]


# ---------------------------------------------------------------------------
# Admin write endpoints
# ---------------------------------------------------------------------------


@elected_officials_router.post(
    "",
    response_model=ElectedOfficialDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_official_endpoint(
    body: ElectedOfficialCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> ElectedOfficialDetailResponse:
    """Create a new elected official record.

    Requires admin authentication.
    """
    try:
        official = await create_official(
            session,
            boundary_type=body.boundary_type,
            district_identifier=body.district_identifier,
            full_name=body.full_name,
            first_name=body.first_name,
            last_name=body.last_name,
            party=body.party,
            title=body.title,
            photo_url=body.photo_url,
            term_start_date=body.term_start_date,
            term_end_date=body.term_end_date,
            last_election_date=body.last_election_date,
            next_election_date=body.next_election_date,
            website=body.website,
            email=body.email,
            phone=body.phone,
            office_address=body.office_address,
            external_ids=body.external_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error creating official: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error creating elected official.",
        ) from e
    logger.info(f"Admin {current_user.username} created official {official.id}")
    return ElectedOfficialDetailResponse.model_validate(official)


# ---------------------------------------------------------------------------
# Parameterized routes (/{official_id} paths AFTER fixed-prefix routes)
# ---------------------------------------------------------------------------


@elected_officials_router.get(
    "/{official_id}",
    response_model=ElectedOfficialDetailResponse,
)
async def get_official_detail(
    official_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> ElectedOfficialDetailResponse:
    """Get elected official detail including source records.

    No authentication required.
    """
    try:
        official = await get_official(session, official_id)
    except Exception as e:
        logger.error(f"Unexpected error fetching official {official_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching elected official.",
        ) from e
    if official is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elected official not found")
    return ElectedOfficialDetailResponse.model_validate(official)


@elected_officials_router.get(
    "/{official_id}/sources",
    response_model=list[ElectedOfficialSourceResponse],
)
async def get_official_sources(
    official_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> list[ElectedOfficialSourceResponse]:
    """Get all source records linked to an elected official.

    No authentication required. Transparency into data provenance.
    """
    try:
        official = await get_official(session, official_id)
    except Exception as e:
        logger.error(f"Unexpected error fetching official sources: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching official sources.",
        ) from e
    if official is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elected official not found")
    return [ElectedOfficialSourceResponse.model_validate(s) for s in official.sources]


@elected_officials_router.patch(
    "/{official_id}",
    response_model=ElectedOfficialDetailResponse,
)
async def update_official_endpoint(
    official_id: uuid.UUID,
    body: ElectedOfficialUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> ElectedOfficialDetailResponse:
    """Update an elected official record.

    Requires admin authentication. Only provided fields are updated.
    """
    official = await get_official(session, official_id)
    if official is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elected official not found")

    try:
        updates = body.model_dump(exclude_unset=True)
        official = await update_official(session, official, updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error updating official {official_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating elected official.",
        ) from e
    logger.info(f"Admin {current_user.username} updated official {official.id}")
    return ElectedOfficialDetailResponse.model_validate(official)


@elected_officials_router.delete(
    "/{official_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_official_endpoint(
    official_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> None:
    """Delete an elected official and all linked source records.

    Requires admin authentication.
    """
    official = await get_official(session, official_id)
    if official is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elected official not found")

    try:
        await delete_official(session, official)
    except Exception as e:
        logger.error(f"Unexpected error deleting official {official_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error deleting elected official.",
        ) from e
    logger.info(f"Admin {current_user.username} deleted official {official_id}")


@elected_officials_router.post(
    "/{official_id}/approve",
    response_model=ElectedOfficialDetailResponse,
)
async def approve_official_endpoint(
    official_id: uuid.UUID,
    body: ApproveOfficialRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> ElectedOfficialDetailResponse:
    """Approve an elected official record, optionally promoting source data.

    Requires admin authentication. Sets status to 'approved' and records
    who approved and when. If source_id is provided, copies that source's
    normalized fields into the canonical record first.
    """
    official = await get_official(session, official_id)
    if official is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Elected official not found")

    try:
        official = await approve_official(session, official, current_user.id, source_id=body.source_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error approving official {official_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error approving elected official.",
        ) from e
    logger.info(f"Admin {current_user.username} approved official {official.id}")
    return ElectedOfficialDetailResponse.model_validate(official)
