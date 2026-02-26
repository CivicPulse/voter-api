"""Candidate API endpoints.

GET  /elections/{election_id}/candidates — list candidates (public)
POST /elections/{election_id}/candidates — create candidate (admin)
GET  /candidates/{candidate_id}          — candidate detail (public)
PATCH /candidates/{candidate_id}         — update candidate (admin)
DELETE /candidates/{candidate_id}        — delete candidate (admin)
POST  /candidates/{candidate_id}/links   — add link (admin)
DELETE /candidates/{candidate_id}/links/{link_id} — delete link (admin)
"""

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.candidate import (
    CandidateCreateRequest,
    CandidateDetailResponse,
    CandidateLinkCreateRequest,
    CandidateLinkResponse,
    CandidateSummaryResponse,
    CandidateUpdateRequest,
    PaginatedCandidateResponse,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.services import candidate_service, election_service

candidates_router = APIRouter(tags=["candidates"])


# --- Public read endpoints ---


@candidates_router.get(
    "/elections/{election_id}/candidates",
    response_model=PaginatedCandidateResponse,
)
async def list_candidates(
    election_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status: str | None = Query(default=None, description="Filter by filing status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page"),
) -> PaginatedCandidateResponse:
    """List candidates for an election. Public endpoint."""
    # Validate election exists
    election = await election_service.get_election_by_id(session, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found.")

    candidates, total = await candidate_service.list_candidates(
        session,
        election_id,
        status=status,
        page=page,
        page_size=page_size,
    )
    items = [
        CandidateSummaryResponse(
            id=c.id,
            election_id=c.election_id,
            full_name=c.full_name,
            party=c.party,
            photo_url=c.photo_url,
            ballot_order=c.ballot_order,
            filing_status=c.filing_status,
            is_incumbent=c.is_incumbent,
            created_at=c.created_at,
        )
        for c in candidates
    ]
    return PaginatedCandidateResponse(
        items=items,
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)) if total > 0 else 0,
        ),
    )


@candidates_router.get(
    "/candidates/{candidate_id}",
    response_model=CandidateDetailResponse,
)
async def get_candidate(
    candidate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> CandidateDetailResponse:
    """Get candidate detail with links. Public endpoint."""
    response = await candidate_service.get_candidate_with_results(session, candidate_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return response


# --- Admin write endpoints ---


@candidates_router.post(
    "/elections/{election_id}/candidates",
    response_model=CandidateDetailResponse,
    status_code=201,
)
async def create_candidate(
    election_id: uuid.UUID,
    request: CandidateCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> CandidateDetailResponse:
    """Create a candidate for an election. Admin-only."""
    # Validate election exists
    election = await election_service.get_election_by_id(session, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found.")

    try:
        candidate = await candidate_service.create_candidate(session, election_id, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    return candidate_service.build_candidate_detail_response(candidate)


@candidates_router.patch(
    "/candidates/{candidate_id}",
    response_model=CandidateDetailResponse,
)
async def update_candidate(
    candidate_id: uuid.UUID,
    request: CandidateUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> CandidateDetailResponse:
    """Update a candidate. Admin-only."""
    try:
        candidate = await candidate_service.update_candidate(session, candidate_id, request)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    return candidate_service.build_candidate_detail_response(candidate)


@candidates_router.delete(
    "/candidates/{candidate_id}",
    status_code=204,
)
async def delete_candidate(
    candidate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> None:
    """Delete a candidate. Admin-only."""
    deleted = await candidate_service.delete_candidate(session, candidate_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate not found.")


# --- Link management ---


@candidates_router.post(
    "/candidates/{candidate_id}/links",
    response_model=CandidateLinkResponse,
    status_code=201,
)
async def add_candidate_link(
    candidate_id: uuid.UUID,
    request: CandidateLinkCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> CandidateLinkResponse:
    """Add a link to a candidate. Admin-only."""
    link = await candidate_service.add_candidate_link(session, candidate_id, request)
    if link is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    return CandidateLinkResponse(
        id=link.id,
        link_type=link.link_type,
        url=link.url,
        label=link.label,
    )


@candidates_router.delete(
    "/candidates/{candidate_id}/links/{link_id}",
    status_code=204,
)
async def delete_candidate_link(
    candidate_id: uuid.UUID,
    link_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _current_user: Annotated[User, Depends(require_role("admin"))],
) -> None:
    """Delete a link from a candidate. Admin-only."""
    deleted = await candidate_service.delete_candidate_link(session, candidate_id, link_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Candidate or link not found.")
