"""MeetingVideoEmbed model — a video recording link for a meeting or agenda item.

Uses the exclusive belongs-to pattern: two nullable FKs (meeting_id,
agenda_item_id) with a CHECK constraint enforcing exactly one is NOT NULL.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, SoftDeleteMixin, UUIDMixin


class VideoPlatform(enum.StrEnum):
    """Supported video hosting platforms."""

    YOUTUBE = "youtube"
    VIMEO = "vimeo"


class MeetingVideoEmbed(Base, UUIDMixin, SoftDeleteMixin):
    """A video recording link associated with a meeting or agenda item.

    Attributes:
        meeting_id: FK to meetings (nullable — exclusive with agenda_item_id).
        agenda_item_id: FK to agenda_items (nullable — exclusive with meeting_id).
        video_url: Full URL to the YouTube or Vimeo video.
        platform: Detected platform (youtube or vimeo).
        start_seconds: Optional start timestamp in seconds.
        end_seconds: Optional end timestamp in seconds.
        created_at: Record creation timestamp.
    """

    __tablename__ = "meeting_video_embeds"

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
    video_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    start_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "(meeting_id IS NOT NULL AND agenda_item_id IS NULL) OR "
            "(meeting_id IS NULL AND agenda_item_id IS NOT NULL)",
            name="ck_video_embed_parent",
        ),
        CheckConstraint(
            "platform IN ('youtube', 'vimeo')",
            name="ck_video_embed_platform",
        ),
        CheckConstraint(
            "start_seconds IS NULL OR end_seconds IS NULL OR end_seconds > start_seconds",
            name="ck_video_embed_timestamps",
        ),
        Index("ix_meeting_video_embeds_meeting_id", "meeting_id"),
        Index("ix_meeting_video_embeds_agenda_item_id", "agenda_item_id"),
    )
