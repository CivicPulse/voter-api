"""Meeting service — CRUD with approval workflow and visibility filtering."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from voter_api.models.agenda_item import AgendaItem
from voter_api.models.governing_body import GoverningBody
from voter_api.models.meeting import ApprovalStatus, Meeting
from voter_api.models.meeting_attachment import MeetingAttachment
from voter_api.models.meeting_video_embed import MeetingVideoEmbed
from voter_api.models.user import User

_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "meeting_date",
        "location",
        "meeting_type",
        "status",
        "external_source_url",
    }
)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def list_meetings(
    session: AsyncSession,
    *,
    governing_body_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    meeting_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    current_user: User | None = None,
) -> tuple[list[Meeting], int]:
    """List meetings with optional filters and approval-based visibility.

    Non-admin users see only approved meetings + their own pending/rejected.
    Admins see all meetings.

    Args:
        session: Database session.
        governing_body_id: Filter by governing body.
        date_from: Start of date range (inclusive).
        date_to: End of date range (inclusive).
        meeting_type: Filter by meeting type.
        status: Filter by status.
        page: Page number (1-based).
        page_size: Items per page.
        current_user: The authenticated user (for visibility filtering).

    Returns:
        Tuple of (meetings, total count).
    """
    base_filter = Meeting.deleted_at.is_(None)

    query = select(Meeting).where(base_filter).options(selectinload(Meeting.governing_body))
    count_query = select(func.count(Meeting.id)).where(base_filter)

    # Approval-based visibility
    if current_user and current_user.role != "admin":
        visibility = (Meeting.approval_status == ApprovalStatus.APPROVED) | (Meeting.submitted_by == current_user.id)
        query = query.where(visibility)
        count_query = count_query.where(visibility)

    if governing_body_id is not None:
        query = query.where(Meeting.governing_body_id == governing_body_id)
        count_query = count_query.where(Meeting.governing_body_id == governing_body_id)
    if date_from is not None:
        query = query.where(Meeting.meeting_date >= date_from)
        count_query = count_query.where(Meeting.meeting_date >= date_from)
    if date_to is not None:
        query = query.where(Meeting.meeting_date <= date_to)
        count_query = count_query.where(Meeting.meeting_date <= date_to)
    if meeting_type is not None:
        query = query.where(Meeting.meeting_type == meeting_type)
        count_query = count_query.where(Meeting.meeting_type == meeting_type)
    if status is not None:
        query = query.where(Meeting.status == status)
        count_query = count_query.where(Meeting.status == status)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(Meeting.meeting_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    meetings = list(result.scalars().all())

    logger.info(f"Listed {len(meetings)} meetings (total={total}, page={page})")
    return meetings, total


async def get_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    current_user: User | None = None,
) -> Meeting | None:
    """Get a single meeting by ID with child counts.

    Non-admin users can only see approved meetings or their own.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.
        current_user: The authenticated user.

    Returns:
        The Meeting or None if not found / not visible.
    """
    query = (
        select(Meeting)
        .where(Meeting.id == meeting_id, Meeting.deleted_at.is_(None))
        .options(selectinload(Meeting.governing_body))
    )

    result = await session.execute(query)
    meeting = result.scalar_one_or_none()

    if meeting is None:
        return None

    # Visibility check for non-admins
    if (
        current_user
        and current_user.role != "admin"
        and meeting.approval_status != ApprovalStatus.APPROVED
        and meeting.submitted_by != current_user.id
    ):
        return None

    return meeting


async def get_child_counts(session: AsyncSession, meeting_id: uuid.UUID) -> tuple[int, int, int]:
    """Get counts of active child records for a meeting.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.

    Returns:
        Tuple of (agenda_item_count, attachment_count, video_embed_count).
    """
    agenda_count = (
        await session.execute(
            select(func.count(AgendaItem.id)).where(
                AgendaItem.meeting_id == meeting_id,
                AgendaItem.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    attachment_count = (
        await session.execute(
            select(func.count(MeetingAttachment.id)).where(
                MeetingAttachment.meeting_id == meeting_id,
                MeetingAttachment.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    video_count = (
        await session.execute(
            select(func.count(MeetingVideoEmbed.id)).where(
                MeetingVideoEmbed.meeting_id == meeting_id,
                MeetingVideoEmbed.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    return agenda_count, attachment_count, video_count


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def create_meeting(
    session: AsyncSession,
    *,
    data: dict,
    current_user: User,
) -> Meeting:
    """Create a new meeting.

    Admin-created meetings are auto-approved. Contributor-created meetings
    are set to pending.

    Args:
        session: Database session.
        data: Meeting field values.
        current_user: The authenticated user.

    Returns:
        The created Meeting.

    Raises:
        ValueError: If the governing body doesn't exist.
    """
    # Verify governing body exists and is active
    gb = await session.execute(
        select(GoverningBody).where(
            GoverningBody.id == data["governing_body_id"],
            GoverningBody.deleted_at.is_(None),
        )
    )
    if gb.scalar_one_or_none() is None:
        raise ValueError("Governing body not found")

    approval_status = ApprovalStatus.APPROVED if current_user.role == "admin" else ApprovalStatus.PENDING

    meeting = Meeting(
        governing_body_id=data["governing_body_id"],
        meeting_date=data["meeting_date"],
        location=data.get("location"),
        meeting_type=data["meeting_type"],
        status=data["status"],
        external_source_url=data.get("external_source_url"),
        approval_status=approval_status,
        submitted_by=current_user.id,
    )
    session.add(meeting)
    await session.commit()
    await session.refresh(meeting, attribute_names=["governing_body"])
    logger.info(f"Created meeting {meeting.id} (approval={approval_status}, by={current_user.username})")
    return meeting


async def update_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    *,
    data: dict,
    current_user: User,
) -> Meeting:
    """Update a meeting with the given fields.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.
        data: Dict of field_name -> new_value.
        current_user: The authenticated user.

    Returns:
        The updated Meeting.

    Raises:
        ValueError: If the meeting is not found or user lacks permission.
    """
    meeting = await get_meeting(session, meeting_id, current_user)
    if meeting is None:
        raise ValueError(f"Meeting {meeting_id} not found")

    if current_user.role != "admin" and meeting.submitted_by != current_user.id:
        raise ValueError("Permission denied: you may only edit your own meetings")

    for field_name, value in data.items():
        if field_name in _UPDATABLE_FIELDS:
            setattr(meeting, field_name, value)

    await session.commit()
    await session.refresh(meeting, attribute_names=["governing_body"])
    logger.info(f"Updated meeting {meeting.id} by {current_user.username}")
    return meeting


async def delete_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
) -> None:
    """Soft-delete a meeting and cascade to all children.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.

    Raises:
        ValueError: If the meeting is not found.
    """
    result = await session.execute(
        select(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.deleted_at.is_(None),
        )
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise ValueError(f"Meeting {meeting_id} not found")

    now = datetime.now(UTC)
    meeting.deleted_at = now

    # Cascade soft-delete to agenda items
    agenda_result = await session.execute(
        select(AgendaItem).where(
            AgendaItem.meeting_id == meeting_id,
            AgendaItem.deleted_at.is_(None),
        )
    )
    for item in agenda_result.scalars().all():
        item.deleted_at = now

    # Cascade soft-delete to meeting-level attachments
    attachment_result = await session.execute(
        select(MeetingAttachment).where(
            MeetingAttachment.meeting_id == meeting_id,
            MeetingAttachment.deleted_at.is_(None),
        )
    )
    for att in attachment_result.scalars().all():
        att.deleted_at = now

    # Cascade soft-delete to meeting-level video embeds
    video_result = await session.execute(
        select(MeetingVideoEmbed).where(
            MeetingVideoEmbed.meeting_id == meeting_id,
            MeetingVideoEmbed.deleted_at.is_(None),
        )
    )
    for embed in video_result.scalars().all():
        embed.deleted_at = now

    await session.commit()
    logger.info(f"Soft-deleted meeting {meeting_id} with cascade")


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------


async def approve_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    admin_user: User,
) -> Meeting:
    """Approve a pending meeting.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.
        admin_user: The admin performing the approval.

    Returns:
        The approved Meeting.

    Raises:
        ValueError: If not found or not in pending status.
    """
    result = await session.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id, Meeting.deleted_at.is_(None))
        .options(selectinload(Meeting.governing_body))
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise ValueError(f"Meeting {meeting_id} not found")
    if meeting.approval_status != ApprovalStatus.PENDING:
        raise ValueError("Meeting is not in pending status")

    meeting.approval_status = ApprovalStatus.APPROVED
    meeting.approved_by = admin_user.id
    meeting.approved_at = datetime.now(UTC)
    meeting.rejection_reason = None

    await session.commit()
    await session.refresh(meeting, attribute_names=["governing_body"])
    logger.info(f"Admin {admin_user.username} approved meeting {meeting_id}")
    return meeting


async def reject_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    admin_user: User,
    reason: str,
) -> Meeting:
    """Reject a pending meeting.

    Args:
        session: Database session.
        meeting_id: The meeting UUID.
        admin_user: The admin performing the rejection.
        reason: Reason for rejection.

    Returns:
        The rejected Meeting.

    Raises:
        ValueError: If not found or not in pending status.
    """
    result = await session.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id, Meeting.deleted_at.is_(None))
        .options(selectinload(Meeting.governing_body))
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise ValueError(f"Meeting {meeting_id} not found")
    if meeting.approval_status != ApprovalStatus.PENDING:
        raise ValueError("Meeting is not in pending status")

    meeting.approval_status = ApprovalStatus.REJECTED
    meeting.approved_by = admin_user.id
    meeting.approved_at = datetime.now(UTC)
    meeting.rejection_reason = reason

    await session.commit()
    await session.refresh(meeting, attribute_names=["governing_body"])
    logger.info(f"Admin {admin_user.username} rejected meeting {meeting_id}: {reason}")
    return meeting
