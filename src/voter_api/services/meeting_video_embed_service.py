"""Video embed service — CRUD with URL validation and platform detection."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.meetings.validators import validate_video_timestamps, validate_video_url
from voter_api.models.agenda_item import AgendaItem
from voter_api.models.meeting import Meeting
from voter_api.models.meeting_video_embed import MeetingVideoEmbed

_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "video_url",
        "start_seconds",
        "end_seconds",
    }
)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def list_embeds(
    session: AsyncSession,
    *,
    meeting_id: uuid.UUID | None = None,
    agenda_item_id: uuid.UUID | None = None,
) -> list[MeetingVideoEmbed]:
    """List active video embeds filtered by parent.

    Args:
        session: Database session.
        meeting_id: Filter by meeting (direct meeting-level embeds).
        agenda_item_id: Filter by agenda item.

    Returns:
        List of MeetingVideoEmbed.
    """
    query = select(MeetingVideoEmbed).where(MeetingVideoEmbed.deleted_at.is_(None))

    if agenda_item_id is not None:
        query = query.where(MeetingVideoEmbed.agenda_item_id == agenda_item_id)
    elif meeting_id is not None:
        query = query.where(MeetingVideoEmbed.meeting_id == meeting_id)

    query = query.order_by(MeetingVideoEmbed.created_at.desc())
    result = await session.execute(query)
    embeds = list(result.scalars().all())
    logger.info(f"Listed {len(embeds)} video embeds")
    return embeds


async def get_embed(
    session: AsyncSession,
    embed_id: uuid.UUID,
) -> MeetingVideoEmbed | None:
    """Get a single video embed by ID.

    Args:
        session: Database session.
        embed_id: The video embed UUID.

    Returns:
        The MeetingVideoEmbed or None.
    """
    result = await session.execute(
        select(MeetingVideoEmbed).where(
            MeetingVideoEmbed.id == embed_id,
            MeetingVideoEmbed.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def create_embed(
    session: AsyncSession,
    *,
    data: dict,
    meeting_id: uuid.UUID | None = None,
    agenda_item_id: uuid.UUID | None = None,
) -> MeetingVideoEmbed:
    """Create a new video embed with URL validation.

    Args:
        session: Database session.
        data: Video embed field values.
        meeting_id: Parent meeting (exclusive with agenda_item_id).
        agenda_item_id: Parent agenda item (exclusive with meeting_id).

    Returns:
        The created MeetingVideoEmbed.

    Raises:
        ValueError: If URL is invalid or parent not found.
    """
    video_url = data["video_url"]
    is_valid, platform = validate_video_url(video_url)
    if not is_valid:
        raise ValueError("Invalid video URL. Must be a YouTube or Vimeo URL.")
    assert platform is not None  # Guaranteed by is_valid check

    start_seconds = data.get("start_seconds")
    end_seconds = data.get("end_seconds")
    if not validate_video_timestamps(start_seconds, end_seconds):
        raise ValueError("Invalid timestamps: end must be greater than start")

    # Validate exactly one parent is provided
    if (meeting_id is None) == (agenda_item_id is None):
        raise ValueError("Exactly one of meeting_id or agenda_item_id must be provided")

    # Validate parent exists
    if meeting_id is not None:
        await _require_meeting(session, meeting_id)
    if agenda_item_id is not None:
        await _require_agenda_item(session, agenda_item_id)

    embed = MeetingVideoEmbed(
        meeting_id=meeting_id,
        agenda_item_id=agenda_item_id,
        video_url=video_url,
        platform=platform,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
    )
    session.add(embed)
    await session.commit()
    await session.refresh(embed)
    logger.info(f"Created video embed {embed.id} ({platform}) for {video_url}")
    return embed


async def update_embed(
    session: AsyncSession,
    embed_id: uuid.UUID,
    *,
    data: dict,
) -> MeetingVideoEmbed:
    """Update a video embed with the given fields.

    Args:
        session: Database session.
        embed_id: The video embed UUID.
        data: Dict of field_name -> new_value.

    Returns:
        The updated MeetingVideoEmbed.

    Raises:
        ValueError: If not found or invalid URL.
    """
    embed = await get_embed(session, embed_id)
    if embed is None:
        raise ValueError(f"Video embed {embed_id} not found")

    # If URL is changing, re-validate and derive platform
    if "video_url" in data:
        is_valid, platform = validate_video_url(data["video_url"])
        if not is_valid:
            raise ValueError("Invalid video URL. Must be a YouTube or Vimeo URL.")
        assert platform is not None  # Guaranteed by is_valid check
        embed.platform = platform

    # Validate timestamps
    start = data.get("start_seconds", embed.start_seconds)
    end = data.get("end_seconds", embed.end_seconds)
    if not validate_video_timestamps(start, end):
        raise ValueError("Invalid timestamps: end must be greater than start")

    for field_name, value in data.items():
        if field_name in _UPDATABLE_FIELDS:
            setattr(embed, field_name, value)

    await session.commit()
    await session.refresh(embed)
    logger.info(f"Updated video embed {embed_id}")
    return embed


async def delete_embed(
    session: AsyncSession,
    embed_id: uuid.UUID,
) -> None:
    """Soft-delete a video embed.

    Args:
        session: Database session.
        embed_id: The video embed UUID.

    Raises:
        ValueError: If not found.
    """
    embed = await get_embed(session, embed_id)
    if embed is None:
        raise ValueError(f"Video embed {embed_id} not found")

    embed.deleted_at = datetime.now(UTC)
    await session.commit()
    logger.info(f"Soft-deleted video embed {embed_id}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_meeting(session: AsyncSession, meeting_id: uuid.UUID) -> None:
    result = await session.execute(select(Meeting.id).where(Meeting.id == meeting_id, Meeting.deleted_at.is_(None)))
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Meeting {meeting_id} not found")


async def _require_agenda_item(session: AsyncSession, agenda_item_id: uuid.UUID) -> None:
    result = await session.execute(
        select(AgendaItem.id).where(
            AgendaItem.id == agenda_item_id,
            AgendaItem.deleted_at.is_(None),
        )
    )
    if result.scalar_one_or_none() is None:
        raise ValueError(f"Agenda item {agenda_item_id} not found")
