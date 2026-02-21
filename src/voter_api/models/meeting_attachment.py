"""MeetingAttachment model — a file associated with a meeting or agenda item.

Uses the exclusive belongs-to pattern: two nullable FKs (meeting_id,
agenda_item_id) with a CHECK constraint enforcing exactly one is NOT NULL.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, SoftDeleteMixin, UUIDMixin


class MeetingAttachment(Base, UUIDMixin, SoftDeleteMixin):
    """A file attachment associated with a meeting or agenda item.

    Attributes:
        meeting_id: FK to meetings (nullable — exclusive with agenda_item_id).
        agenda_item_id: FK to agenda_items (nullable — exclusive with meeting_id).
        original_filename: The original uploaded filename.
        stored_path: Path/key in the storage backend.
        file_size: File size in bytes.
        content_type: MIME type (e.g., application/pdf).
        created_at: Upload timestamp.
    """

    __tablename__ = "meeting_attachments"

    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id"),
        nullable=True,
    )
    agenda_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agenda_items.id"),
        nullable=True,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR "
            "(meeting_id IS NULL AND agenda_item_id IS NOT NULL)",
            name="ck_attachment_parent",
        ),
        Index("ix_meeting_attachments_meeting_id", "meeting_id"),
        Index("ix_meeting_attachments_agenda_item_id", "agenda_item_id"),
        Index("ix_meeting_attachments_filename", "original_filename"),
    )
