"""Agenda item service — CRUD with gap-based ordering and reorder support."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.agenda_item import AgendaItem
from voter_api.models.meeting import Meeting
from voter_api.models.meeting_attachment import MeetingAttachment
from voter_api.models.meeting_video_embed import MeetingVideoEmbed

_ORDER_GAP = 10

_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "action_taken",
        "disposition",
    }
)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def list_items(
    session: AsyncSession,
    meeting_id: uuid.UUID,
) -> list[AgendaItem]:
    """List all active agenda items for a meeting, ordered by display_order.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.

    Returns:
        List of AgendaItem ordered by display_order.

    Raises:
        ValueError: If the meeting does not exist.
    """
    await _require_meeting(session, meeting_id)

    result = await session.execute(
        select(AgendaItem)
        .where(
            AgendaItem.meeting_id == meeting_id,
            AgendaItem.deleted_at.is_(None),
        )
        .order_by(AgendaItem.display_order)
    )
    items = list(result.scalars().all())
    logger.info(f"Listed {len(items)} agenda items for meeting {meeting_id}")
    return items


async def get_item(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
) -> AgendaItem | None:
    """Get a single agenda item by ID.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.
        item_id: The agenda item UUID.

    Returns:
        The AgendaItem or None if not found.
    """
    result = await session.execute(
        select(AgendaItem).where(
            AgendaItem.id == item_id,
            AgendaItem.meeting_id == meeting_id,
            AgendaItem.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_item_child_counts(session: AsyncSession, item_id: uuid.UUID) -> tuple[int, int]:
    """Get counts of active child records for an agenda item.

    Args:
        session: Database session.
        item_id: The agenda item UUID.

    Returns:
        Tuple of (attachment_count, video_embed_count).
    """
    attachment_count = (
        await session.execute(
            select(func.count(MeetingAttachment.id)).where(
                MeetingAttachment.agenda_item_id == item_id,
                MeetingAttachment.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    video_count = (
        await session.execute(
            select(func.count(MeetingVideoEmbed.id)).where(
                MeetingVideoEmbed.agenda_item_id == item_id,
                MeetingVideoEmbed.deleted_at.is_(None),
            )
        )
    ).scalar_one()

    return attachment_count, video_count


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def create_item(
    session: AsyncSession,
    *,
    meeting_id: uuid.UUID,
    data: dict,
) -> AgendaItem:
    """Create a new agenda item with gap-based ordering.

    If display_order is not provided, the item is appended to the end
    with a gap of ORDER_GAP from the current maximum.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.
        data: Agenda item field values.

    Returns:
        The created AgendaItem.

    Raises:
        ValueError: If the meeting does not exist.
    """
    await _require_meeting(session, meeting_id)

    display_order = data.get("display_order")
    if display_order is None:
        max_order = (
            await session.execute(
                select(func.max(AgendaItem.display_order)).where(
                    AgendaItem.meeting_id == meeting_id,
                    AgendaItem.deleted_at.is_(None),
                )
            )
        ).scalar_one()
        display_order = (max_order or 0) + _ORDER_GAP

    item = AgendaItem(
        meeting_id=meeting_id,
        title=data["title"],
        description=data.get("description"),
        action_taken=data.get("action_taken"),
        disposition=data.get("disposition"),
        display_order=display_order,
    )
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError(f"display_order {display_order} already exists for this meeting") from exc
    await session.refresh(item)
    logger.info(f"Created agenda item {item.id} at order {display_order} for meeting {meeting_id}")
    return item


async def update_item(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    data: dict,
) -> AgendaItem:
    """Update an agenda item with the given fields.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.
        item_id: The agenda item UUID.
        data: Dict of field_name -> new_value.

    Returns:
        The updated AgendaItem.

    Raises:
        ValueError: If the item is not found.
    """
    item = await get_item(session, meeting_id, item_id)
    if item is None:
        raise ValueError(f"Agenda item {item_id} not found")

    for field_name, value in data.items():
        if field_name in _UPDATABLE_FIELDS:
            setattr(item, field_name, value)

    await session.commit()
    await session.refresh(item)
    logger.info(f"Updated agenda item {item_id}")
    return item


async def delete_item(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
) -> None:
    """Soft-delete an agenda item.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.
        item_id: The agenda item UUID.

    Raises:
        ValueError: If the item is not found.
    """
    item = await get_item(session, meeting_id, item_id)
    if item is None:
        raise ValueError(f"Agenda item {item_id} not found")

    now = datetime.now(UTC)
    item.deleted_at = now

    # Cascade soft-delete to child attachments
    attachment_result = await session.execute(
        select(MeetingAttachment).where(
            MeetingAttachment.agenda_item_id == item_id,
            MeetingAttachment.deleted_at.is_(None),
        )
    )
    for att in attachment_result.scalars().all():
        att.deleted_at = now

    # Cascade soft-delete to child video embeds
    video_result = await session.execute(
        select(MeetingVideoEmbed).where(
            MeetingVideoEmbed.agenda_item_id == item_id,
            MeetingVideoEmbed.deleted_at.is_(None),
        )
    )
    for embed in video_result.scalars().all():
        embed.deleted_at = now

    await session.commit()
    logger.info(f"Soft-deleted agenda item {item_id} with cascade")


async def reorder_items(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    item_ids: list[uuid.UUID],
) -> list[AgendaItem]:
    """Atomically reorder agenda items by assigning new display_order values.

    Args:
        session: Database session.
        meeting_id: The parent meeting UUID.
        item_ids: Ordered list of item UUIDs defining the new order.

    Returns:
        The reordered list of AgendaItem.

    Raises:
        ValueError: If any item ID is not found or doesn't belong to this meeting.
    """
    await _require_meeting(session, meeting_id)

    # Fetch all active items for this meeting
    result = await session.execute(
        select(AgendaItem).where(
            AgendaItem.meeting_id == meeting_id,
            AgendaItem.deleted_at.is_(None),
        )
    )
    existing_items = {item.id: item for item in result.scalars().all()}

    # Reject duplicate IDs
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Duplicate item IDs are not allowed")

    # Validate all provided IDs exist and belong to this meeting
    for item_id in item_ids:
        if item_id not in existing_items:
            raise ValueError(f"Agenda item {item_id} not found in meeting {meeting_id}")

    # Require all active items to be included
    missing = set(existing_items.keys()) - set(item_ids)
    if missing:
        raise ValueError(f"All active agenda items must be included. Missing: {missing}")

    # Assign new order values with gaps
    for idx, item_id in enumerate(item_ids):
        existing_items[item_id].display_order = (idx + 1) * _ORDER_GAP

    await session.commit()

    # Re-fetch in order
    reordered = await list_items(session, meeting_id)
    logger.info(f"Reordered {len(item_ids)} agenda items for meeting {meeting_id}")
    return reordered


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def require_agenda_item_in_meeting(
    session: AsyncSession,
    meeting_id: uuid.UUID,
    agenda_item_id: uuid.UUID,
) -> None:
    """Verify that an agenda item exists and belongs to the given meeting.

    Args:
        session: Database session.
        meeting_id: The expected parent meeting UUID.
        agenda_item_id: The agenda item UUID.

    Raises:
        ValueError: If the agenda item is not found or doesn't belong to the meeting.
    """
    result = await session.execute(
        select(AgendaItem.id).where(
            AgendaItem.id == agenda_item_id,
            AgendaItem.meeting_id == meeting_id,
            AgendaItem.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Agenda item {agenda_item_id} not found in meeting {meeting_id}")


async def _require_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> None:
    """Verify that a meeting exists and is active.

    Raises:
        ValueError: If the meeting is not found.
    """
    result = await session.execute(
        select(Meeting.id).where(
            Meeting.id == meeting_id,
            Meeting.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Meeting {meeting_id} not found")
