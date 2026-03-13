"""Absentee ballot application API endpoints.

GET /absentee (list), GET /absentee/stats, GET /absentee/by-voter/{vrn},
GET /absentee/{ballot_app_id} (detail).
"""

import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.absentee import (
    AbsenteeBallotDetailResponse,
    AbsenteeStatsResponse,
    PaginatedAbsenteeResponse,
)
from voter_api.schemas.common import PaginationMeta, PaginationParams
from voter_api.services import absentee_service

absentee_router = APIRouter(prefix="/absentee", tags=["absentee"])


@absentee_router.get("")
async def list_absentee_ballots(
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pagination: Annotated[PaginationParams, Depends()],
    county: str | None = None,
    application_status: str | None = None,
    ballot_status: str | None = None,
    party: str | None = None,
) -> PaginatedAbsenteeResponse:
    """List absentee ballot applications with optional filters (admin/analyst only)."""
    records, total = await absentee_service.query_absentee_ballots(
        session,
        county=county,
        application_status=application_status,
        ballot_status=ballot_status,
        party=party,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedAbsenteeResponse(
        items=[AbsenteeBallotDetailResponse.model_validate(r) for r in records],
        pagination=PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=max(1, math.ceil(total / pagination.page_size)),
        ),
    )


@absentee_router.get("/stats")
async def get_absentee_stats(
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    county: str | None = None,
) -> AbsenteeStatsResponse:
    """Get aggregate statistics for absentee ballot applications (admin/analyst only)."""
    stats = await absentee_service.get_absentee_stats(session, county=county)
    return AbsenteeStatsResponse(**stats)


@absentee_router.get("/by-voter/{voter_registration_number}")
async def get_voter_absentee_ballots(
    voter_registration_number: str,
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pagination: Annotated[PaginationParams, Depends()],
) -> PaginatedAbsenteeResponse:
    """Get absentee ballot applications for a specific voter (admin/analyst only)."""
    records, total = await absentee_service.query_absentee_ballots(
        session,
        voter_registration_number=voter_registration_number,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedAbsenteeResponse(
        items=[AbsenteeBallotDetailResponse.model_validate(r) for r in records],
        pagination=PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=max(1, math.ceil(total / pagination.page_size)),
        ),
    )


@absentee_router.get("/{ballot_app_id}")
async def get_absentee_ballot_detail(
    ballot_app_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AbsenteeBallotDetailResponse:
    """Get full detail for a single absentee ballot application (admin/analyst only)."""
    record = await absentee_service.get_absentee_ballot(session, ballot_app_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Absentee ballot application not found",
        )
    return AbsenteeBallotDetailResponse.model_validate(record)
