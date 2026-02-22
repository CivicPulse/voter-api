"""Meetings API endpoints with approval workflow."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.meeting import (
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingRejectRequest,
    MeetingSummaryResponse,
    MeetingUpdateRequest,
    PaginatedMeetingResponse,
)
from voter_api.schemas.meeting_search import (
    PaginatedSearchResultResponse,
    SearchResultItem,
)
from voter_api.services.meeting_search_service import search_meetings
from voter_api.services.meeting_service import (
    approve_meeting,
    create_meeting,
    delete_meeting,
    get_child_counts,
    get_meeting,
    list_meetings,
    reject_meeting,
    update_meeting,
)

meetings_router = APIRouter(
    prefix="/meetings",
    tags=["meetings"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summary_from_meeting(meeting: object) -> MeetingSummaryResponse:
    """Build a summary response, resolving governing_body_name."""
    data = MeetingSummaryResponse.model_validate(meeting)
    if hasattr(meeting, "governing_body") and meeting.governing_body is not None:
        data.governing_body_name = meeting.governing_body.name  # type: ignore[union-attr]
    return data


async def _detail_from_meeting(session: AsyncSession, meeting: object) -> MeetingDetailResponse:
    """Build a detail response with child counts."""
    detail = MeetingDetailResponse.model_validate(meeting)
    if hasattr(meeting, "governing_body") and meeting.governing_body is not None:
        detail.governing_body_name = meeting.governing_body.name  # type: ignore[union-attr]
    agenda_count, attachment_count, video_count = await get_child_counts(session, detail.id)
    detail.agenda_item_count = agenda_count
    detail.attachment_count = attachment_count
    detail.video_embed_count = video_count
    return detail


# ---------------------------------------------------------------------------
# List and search endpoints (fixed-prefix routes FIRST)
# ---------------------------------------------------------------------------


@meetings_router.get(
    "",
)
async def list_all_meetings(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
    governing_body_id: Annotated[uuid.UUID | None, Query(description="Filter by governing body")] = None,
    date_from: Annotated[datetime | None, Query(description="Start of date range")] = None,
    date_to: Annotated[datetime | None, Query(description="End of date range")] = None,
    meeting_type: Annotated[str | None, Query(description="Filter by meeting type")] = None,
    meeting_status: Annotated[str | None, Query(alias="status", description="Filter by status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedMeetingResponse:
    """List meetings with optional filters and approval-based visibility."""
    meetings, total = await list_meetings(
        session,
        governing_body_id=governing_body_id,
        date_from=date_from,
        date_to=date_to,
        meeting_type=meeting_type,
        status=meeting_status,
        page=page,
        page_size=page_size,
        current_user=current_user,
    )
    return PaginatedMeetingResponse(
        items=[_summary_from_meeting(m) for m in meetings],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        ),
    )


@meetings_router.get(
    "/search",
)
async def search_meetings_endpoint(
    q: Annotated[str, Query(min_length=2, description="Search query (min 2 characters)")],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedSearchResultResponse:
    """Full-text search across agenda items and attachment filenames."""
    try:
        items, total = await search_meetings(
            session,
            query=q,
            page=page,
            page_size=page_size,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e
    return PaginatedSearchResultResponse(
        items=[SearchResultItem(**item) for item in items],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        ),
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@meetings_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting_endpoint(
    body: MeetingCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin", "contributor"))],
) -> MeetingDetailResponse:
    """Create a new meeting.

    Admin-created meetings are auto-approved. Contributor-created meetings
    are set to pending.
    """
    try:
        meeting = await create_meeting(
            session,
            data=body.model_dump(),
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"User {current_user.username} created meeting {meeting.id}")
    return await _detail_from_meeting(session, meeting)


# ---------------------------------------------------------------------------
# Approval workflow endpoints (fixed-prefix, before /{id})
# ---------------------------------------------------------------------------


@meetings_router.post(
    "/{meeting_id}/approve",
)
async def approve_meeting_endpoint(
    meeting_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> MeetingDetailResponse:
    """Approve a pending meeting."""
    try:
        meeting = await approve_meeting(session, meeting_id, current_user)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e
    return await _detail_from_meeting(session, meeting)


@meetings_router.post(
    "/{meeting_id}/reject",
)
async def reject_meeting_endpoint(
    meeting_id: uuid.UUID,
    body: MeetingRejectRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> MeetingDetailResponse:
    """Reject a pending meeting with a reason."""
    try:
        meeting = await reject_meeting(session, meeting_id, current_user, body.reason)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e
    return await _detail_from_meeting(session, meeting)


# ---------------------------------------------------------------------------
# Parameterized routes (/{meeting_id} paths AFTER fixed-prefix routes)
# ---------------------------------------------------------------------------


@meetings_router.get(
    "/{meeting_id}",
)
async def get_meeting_detail(
    meeting_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
) -> MeetingDetailResponse:
    """Get meeting detail with child counts."""
    meeting = await get_meeting(session, meeting_id, current_user)
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found",
        )
    return await _detail_from_meeting(session, meeting)


@meetings_router.patch(
    "/{meeting_id}",
)
async def update_meeting_endpoint(
    meeting_id: uuid.UUID,
    body: MeetingUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin", "contributor"))],
) -> MeetingDetailResponse:
    """Update a meeting. Only provided fields are updated."""
    try:
        meeting = await update_meeting(
            session,
            meeting_id,
            data=body.model_dump(exclude_unset=True),
            current_user=current_user,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return await _detail_from_meeting(session, meeting)


@meetings_router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_meeting_endpoint(
    meeting_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> None:
    """Soft-delete a meeting and all child records."""
    try:
        await delete_meeting(session, meeting_id, current_user=current_user)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"Admin {current_user.username} deleted meeting {meeting_id}")
