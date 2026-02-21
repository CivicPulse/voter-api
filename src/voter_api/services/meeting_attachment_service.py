"""Meeting attachment service — upload, download, list, and soft-delete."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.meetings.storage import FileStorage
from voter_api.lib.meetings.validators import (
    get_allowed_extensions_display,
    validate_file_content_type,
    validate_file_extension,
)
from voter_api.models.agenda_item import AgendaItem
from voter_api.models.meeting import Meeting
from voter_api.models.meeting_attachment import MeetingAttachment

# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def list_attachments(
    session: AsyncSession,
    *,
    meeting_id: uuid.UUID | None = None,
    agenda_item_id: uuid.UUID | None = None,
) -> list[MeetingAttachment]:
    """List active attachments filtered by parent.

    Args:
        session: Database session.
        meeting_id: Filter by meeting (direct meeting-level attachments).
        agenda_item_id: Filter by agenda item.

    Returns:
        List of MeetingAttachment.
    """
    query = select(MeetingAttachment).where(MeetingAttachment.deleted_at.is_(None))

    if agenda_item_id is not None:
        query = query.where(MeetingAttachment.agenda_item_id == agenda_item_id)
    elif meeting_id is not None:
        query = query.where(MeetingAttachment.meeting_id == meeting_id)

    query = query.order_by(MeetingAttachment.created_at.desc())
    result = await session.execute(query)
    attachments = list(result.scalars().all())
    logger.info(f"Listed {len(attachments)} attachments")
    return attachments


async def get_attachment(
    session: AsyncSession,
    attachment_id: uuid.UUID,
) -> MeetingAttachment | None:
    """Get a single attachment by ID.

    Args:
        session: Database session.
        attachment_id: The attachment UUID.

    Returns:
        The MeetingAttachment or None.
    """
    result = await session.execute(
        select(MeetingAttachment).where(
            MeetingAttachment.id == attachment_id,
            MeetingAttachment.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


async def upload_attachment(
    session: AsyncSession,
    *,
    file_content: bytes,
    filename: str,
    content_type: str,
    meeting_id: uuid.UUID | None = None,
    agenda_item_id: uuid.UUID | None = None,
    storage: FileStorage,
    max_file_size_bytes: int = 50 * 1024 * 1024,
) -> MeetingAttachment:
    """Upload a file attachment to a meeting or agenda item.

    Args:
        session: Database session.
        file_content: Raw file bytes.
        filename: Original filename.
        content_type: MIME type.
        meeting_id: Parent meeting (exclusive with agenda_item_id).
        agenda_item_id: Parent agenda item (exclusive with meeting_id).
        storage: File storage backend.
        max_file_size_bytes: Maximum allowed file size in bytes.

    Returns:
        The created MeetingAttachment.

    Raises:
        ValueError: If validation fails (format, size, parent not found).
    """
    # Validate exactly one parent is provided
    if (meeting_id is None) == (agenda_item_id is None):
        raise ValueError("Exactly one of meeting_id or agenda_item_id must be provided")

    # Validate file format — reject if either MIME type or extension is invalid
    if not validate_file_content_type(content_type) or not validate_file_extension(filename):
        allowed = get_allowed_extensions_display()
        raise ValueError(f"Unsupported file format. Allowed: {allowed}")

    # Validate file size
    if len(file_content) > max_file_size_bytes:
        raise ValueError(f"File exceeds maximum size of {max_file_size_bytes // (1024 * 1024)} MB")

    # Validate parent exists
    if meeting_id is not None:
        await _require_meeting(session, meeting_id)
    if agenda_item_id is not None:
        await _require_agenda_item(session, agenda_item_id)

    # Store the file
    stored_path = await storage.save(file_content, filename)

    attachment = MeetingAttachment(
        meeting_id=meeting_id,
        agenda_item_id=agenda_item_id,
        original_filename=filename,
        stored_path=stored_path,
        file_size=len(file_content),
        content_type=content_type,
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    logger.info(f"Uploaded attachment {attachment.id}: {filename} ({len(file_content)} bytes)")
    return attachment


async def download_attachment(
    session: AsyncSession,
    attachment_id: uuid.UUID,
    storage: FileStorage,
) -> tuple[bytes, MeetingAttachment]:
    """Download an attachment's file content.

    Args:
        session: Database session.
        attachment_id: The attachment UUID.
        storage: File storage backend.

    Returns:
        Tuple of (file_bytes, attachment_metadata).

    Raises:
        ValueError: If attachment not found.
    """
    attachment = await get_attachment(session, attachment_id)
    if attachment is None:
        raise ValueError(f"Attachment {attachment_id} not found")

    content = await storage.load(attachment.stored_path)
    return content, attachment


async def delete_attachment(
    session: AsyncSession,
    attachment_id: uuid.UUID,
) -> None:
    """Soft-delete an attachment (file preserved on disk).

    Args:
        session: Database session.
        attachment_id: The attachment UUID.

    Raises:
        ValueError: If attachment not found.
    """
    attachment = await get_attachment(session, attachment_id)
    if attachment is None:
        raise ValueError(f"Attachment {attachment_id} not found")

    attachment.deleted_at = datetime.now(UTC)
    await session.commit()
    logger.info(f"Soft-deleted attachment {attachment_id}")


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
