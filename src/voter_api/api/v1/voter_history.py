"""Voter history API endpoints.

GET /voters/{reg_num}/history, GET /elections/{id}/participation,
GET /elections/{id}/participation/stats.
"""

import math
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter_history import (
    ElectionParticipationRecord,
    PaginatedElectionParticipationResponse,
    PaginatedVoterHistoryResponse,
    ParticipationStatsResponse,
    VoterHistoryRecord,
)
from voter_api.services import voter_history_service

voter_history_router = APIRouter(tags=["voter-history"])


@voter_history_router.get(
    "/voters/{voter_registration_number}/history",
    response_model=PaginatedVoterHistoryResponse,
)
async def get_voter_history(
    voter_registration_number: str,
    current_user: Annotated[User, Depends(require_role("analyst", "admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    election_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    county: str | None = None,
    ballot_style: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedVoterHistoryResponse:
    """Get a voter's participation history with optional filtering."""
    records, total = await voter_history_service.get_voter_history(
        session,
        voter_registration_number,
        election_type=election_type,
        date_from=date_from,
        date_to=date_to,
        county=county,
        ballot_style=ballot_style,
        page=page,
        page_size=page_size,
    )
    return PaginatedVoterHistoryResponse(
        items=[VoterHistoryRecord.model_validate(r) for r in records],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


@voter_history_router.get(
    "/elections/{election_id}/participation",
    response_model=PaginatedElectionParticipationResponse,
)
async def list_election_participants(
    election_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("analyst", "admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    county: str | None = None,
    ballot_style: str | None = None,
    absentee: bool | None = None,
    provisional: bool | None = None,
    supplemental: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedElectionParticipationResponse:
    """List voters who participated in an election."""
    try:
        records, total = await voter_history_service.list_election_participants(
            session,
            election_id,
            county=county,
            ballot_style=ballot_style,
            absentee=absentee,
            provisional=provisional,
            supplemental=supplemental,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        ) from exc
    return PaginatedElectionParticipationResponse(
        items=[ElectionParticipationRecord.model_validate(r) for r in records],
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


@voter_history_router.get(
    "/elections/{election_id}/participation/stats",
    response_model=ParticipationStatsResponse,
)
async def get_election_participation_stats(
    election_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ParticipationStatsResponse:
    """Get aggregate participation statistics for an election."""
    try:
        return await voter_history_service.get_participation_stats(session, election_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        ) from exc
