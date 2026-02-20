"""AgendaItem model — an ordered item on a meeting's agenda.

Includes a PostgreSQL generated tsvector column for full-text search with
weighted fields (title=A, description=B) and a GIN index.
"""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    Computed,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Disposition(enum.StrEnum):
    """Possible outcomes for an agenda item."""

    APPROVED = "approved"
    DENIED = "denied"
    TABLED = "tabled"
    NO_ACTION = "no_action"
    INFORMATIONAL = "informational"


class AgendaItem(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """An ordered item on a meeting's agenda.

    Attributes:
        meeting_id: FK to the parent meeting.
        title: Agenda item title.
        description: Detailed description.
        action_taken: Free-text record of action taken.
        disposition: Outcome (approved, denied, tabled, etc.).
        display_order: Position within the meeting agenda.
        search_vector: Generated tsvector for full-text search.
    """

    __tablename__ = "agenda_items"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meetings.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(20), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)

    # Generated tsvector column for full-text search
    search_vector = Column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(description, '')), 'B')",
            persisted=True,
        ),
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(  # noqa: F821
        back_populates="agenda_items",
        lazy="selectin",
    )
    attachments: Mapped[list["MeetingAttachment"]] = relationship(  # noqa: F821
        primaryjoin="and_(AgendaItem.id == MeetingAttachment.agenda_item_id, MeetingAttachment.deleted_at.is_(None))",
        lazy="noload",
        viewonly=True,
    )
    video_embeds: Mapped[list["MeetingVideoEmbed"]] = relationship(  # noqa: F821
        primaryjoin="and_(AgendaItem.id == MeetingVideoEmbed.agenda_item_id, MeetingVideoEmbed.deleted_at.is_(None))",
        lazy="noload",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('approved', 'denied', 'tabled', 'no_action', 'informational')",
            name="ck_agenda_item_disposition",
        ),
        UniqueConstraint(
            "meeting_id",
            "display_order",
            name="uq_agenda_item_meeting_order",
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_agenda_items_meeting_id", "meeting_id"),
        Index("ix_agenda_items_search_vector", "search_vector", postgresql_using="gin"),
    )
