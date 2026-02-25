"""Voter history API endpoints.

GET /voters/{reg_num}/history, GET /elections/{id}/participation,
GET /elections/{id}/participation/stats.
"""

import math
import uuid
from datetime import date
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy import Row

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.lib.normalize import normalize_registration_number
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter_history import (
    ElectionParticipationRecord,
    PaginatedElectionParticipationResponse,
    PaginatedVoterHistoryResponse,
    ParticipationFilters,
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
    voter_registration_number = normalize_registration_number(voter_registration_number)
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
    # Resolve election IDs for records that don't have a stored one
    unresolved = [r for r in records if r.election_id is None]
    election_id_map = await voter_history_service.resolve_election_ids(session, unresolved) if unresolved else {}

    items = []
    for r in records:
        item = VoterHistoryRecord.model_validate(r)
        if item.election_id is None:
            item.election_id = election_id_map.get((r.election_date, r.normalized_election_type))
        items.append(item)

    return PaginatedVoterHistoryResponse(
        items=items,
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
    q: Annotated[str | None, Query(max_length=500)] = None,
    county: str | None = None,
    ballot_style: str | None = None,
    absentee: bool | None = None,
    provisional: bool | None = None,
    supplemental: bool | None = None,
    county_precinct: str | None = None,
    congressional_district: str | None = None,
    state_senate_district: str | None = None,
    state_house_district: str | None = None,
    county_commission_district: str | None = None,
    school_board_district: str | None = None,
    voter_status: str | None = None,
    has_district_mismatch: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PaginatedElectionParticipationResponse:
    """List voters who participated in an election."""
    filters = ParticipationFilters(
        county=county,
        ballot_style=ballot_style,
        absentee=absentee,
        provisional=provisional,
        supplemental=supplemental,
        q=q,
        county_precinct=county_precinct,
        congressional_district=congressional_district,
        state_senate_district=state_senate_district,
        state_house_district=state_house_district,
        county_commission_district=county_commission_district,
        school_board_district=school_board_district,
        voter_status=voter_status,
        has_district_mismatch=has_district_mismatch,
    )
    try:
        results, total, voter_details_included = await voter_history_service.list_election_participants(
            session,
            election_id,
            filters=filters,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Election not found",
        ) from exc

    items = []
    if voter_details_included:
        # JOIN path: rows are (VoterHistory, voter_id, first_name, last_name, has_district_mismatch)
        for row in results:
            typed_row = cast("Row[Any]", row)
            vh = typed_row[0]
            item = ElectionParticipationRecord.model_validate(vh)
            mapping = typed_row._mapping
            item.voter_id = mapping["voter_id"]
            item.first_name = mapping["first_name"]
            item.last_name = mapping["last_name"]
            item.has_district_mismatch = mapping["has_district_mismatch"]
            items.append(item)
    else:
        # Default path: enrich from separate lookup
        reg_nums = [r.voter_registration_number for r in results]
        voter_detail_map = await voter_history_service.lookup_voter_details(session, reg_nums) if reg_nums else {}

        for r in results:
            item = ElectionParticipationRecord.model_validate(r)
            detail = voter_detail_map.get(r.voter_registration_number)
            if detail:
                item.voter_id = detail.id
                item.first_name = detail.first_name
                item.last_name = detail.last_name
                item.has_district_mismatch = detail.has_district_mismatch
            items.append(item)

    return PaginatedElectionParticipationResponse(
        items=items,
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
    current_user: Annotated[User, Depends(require_role("analyst", "admin"))],
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
