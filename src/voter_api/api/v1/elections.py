"""Election tracking API endpoints.

GET /elections — list elections (US5)
POST /elections — create election (US4)
GET /elections/{id} — election detail (US1)
PATCH /elections/{id} — update election (US4)
GET /elections/{id}/results — JSON results (US1)
GET /elections/{id}/results/geojson — GeoJSON results (US2)
POST /elections/{id}/refresh — manual refresh (US4)
"""

import math
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.lib.election_tracker import FetchError
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.election import (
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionResultsResponse,
    ElectionUpdateRequest,
    PaginatedElectionListResponse,
    RefreshResponse,
)
from voter_api.services import election_service

elections_router = APIRouter(prefix="/elections", tags=["elections"])


# --- US5: List elections ---


@elections_router.get("", response_model=PaginatedElectionListResponse)
async def list_elections(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status: str | None = Query(default=None, description="Filter by status"),
    election_type: str | None = Query(default=None, description="Filter by type"),
    district: str | None = Query(default=None, description="Filter by district (partial match)"),
    date_from: date | None = Query(default=None, description="Filter elections on or after this date"),
    date_to: date | None = Query(default=None, description="Filter elections on or before this date"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
) -> PaginatedElectionListResponse:
    """List elections with optional filters. Public endpoint."""
    items, total = await election_service.list_elections(
        session,
        status=status,
        election_type=election_type,
        district=district,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return PaginatedElectionListResponse(
        items=items,
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)) if total > 0 else 0,
        ),
    )


# --- US4: Admin create ---


@elections_router.post(
    "",
    response_model=ElectionDetailResponse,
    status_code=201,
)
async def create_election(
    request: ElectionCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> ElectionDetailResponse:
    """Create a new election. Admin-only."""
    try:
        election = await election_service.create_election(session, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return election_service._build_detail_response(election)


# --- US1: Election detail ---


@elections_router.get("/{election_id}", response_model=ElectionDetailResponse)
async def get_election(
    election_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ElectionDetailResponse:
    """Get election detail by ID. Public endpoint."""
    election = await election_service.get_election_by_id(session, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found.")
    return election_service._build_detail_response(election)


# --- US4: Admin update ---


@elections_router.patch("/{election_id}", response_model=ElectionDetailResponse)
async def update_election(
    election_id: uuid.UUID,
    request: ElectionUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> ElectionDetailResponse:
    """Update election metadata. Admin-only."""
    election = await election_service.update_election(session, election_id, request)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found.")
    return election_service._build_detail_response(election)


# --- US1: JSON results ---


@elections_router.get("/{election_id}/results", response_model=ElectionResultsResponse)
async def get_election_results(
    election_id: uuid.UUID,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ElectionResultsResponse:
    """Get statewide + county election results as JSON. Public endpoint."""
    result = await election_service.get_election_results(session, election_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Election not found.")

    # Status-dependent Cache-Control header
    cache_ttl = 60 if result.status == "active" else 86400
    response.headers["Cache-Control"] = f"public, max-age={cache_ttl}"

    return result


# --- US2: GeoJSON results ---


@elections_router.get("/{election_id}/results/geojson")
async def get_election_results_geojson(
    election_id: uuid.UUID,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> JSONResponse:
    """Get county-level election results as GeoJSON. Public endpoint."""
    result = await election_service.get_election_results_geojson(session, election_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Election not found.")

    # Status-dependent Cache-Control header
    election = await election_service.get_election_by_id(session, election_id)
    cache_ttl = 60 if election and election.status == "active" else 86400

    return JSONResponse(
        content=result.model_dump(mode="json"),
        media_type="application/geo+json",
        headers={"Cache-Control": f"public, max-age={cache_ttl}"},
    )


# --- US4: Admin manual refresh ---


@elections_router.post("/{election_id}/refresh", response_model=RefreshResponse)
async def refresh_election(
    election_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> RefreshResponse:
    """Trigger manual election results refresh. Admin-only."""
    try:
        return await election_service.refresh_single_election(session, election_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FetchError as e:
        raise HTTPException(
            status_code=502,
            detail="Failed to retrieve results from data source. Please retry later.",
        ) from e
