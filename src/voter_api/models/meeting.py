"""Meeting model — a specific session of a governing body.

Includes approval workflow fields for contributor submissions. Admin-created
meetings default to 'approved'; contributor-created meetings default to 'pending'.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class MeetingType(enum.StrEnum):
    """Meeting type classification."""

    REGULAR = "regular"
    SPECIAL = "special"
    WORK_SESSION = "work_session"
    EMERGENCY = "emergency"
    PUBLIC_HEARING = "public_hearing"


class MeetingStatus(enum.StrEnum):
    """Meeting lifecycle status."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class ApprovalStatus(enum.StrEnum):
    """Approval workflow status for contributor submissions."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Meeting(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A specific meeting session of a governing body.

    Attributes:
        governing_body_id: FK to the parent governing body.
        meeting_date: Date and time of the meeting (with timezone).
        location: Physical or virtual meeting location.
        meeting_type: Classification (regular, special, etc.).
        status: Lifecycle status (scheduled, completed, etc.).
        external_source_url: Link to official government meeting page.
        approval_status: Workflow state (pending, approved, rejected).
        submitted_by: User who created the record.
        approved_by: Admin who approved/rejected the record.
        approved_at: When approval/rejection occurred.
        rejection_reason: Reason for rejection (required on reject).
    """

    __tablename__ = "meetings"

    governing_body_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("governing_bodies.id"),
        nullable=False,
    )
    meeting_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meeting_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    external_source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Approval workflow
    approval_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalStatus.APPROVED,
        server_default="approved",
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    governing_body: Mapped["GoverningBody"] = relationship(  # noqa: F821
        back_populates="meetings",
        lazy="selectin",
    )
    agenda_items: Mapped[list["AgendaItem"]] = relationship(  # noqa: F821
        back_populates="meeting",
        lazy="noload",
    )
    attachments: Mapped[list["MeetingAttachment"]] = relationship(  # noqa: F821
        primaryjoin="and_(Meeting.id == MeetingAttachment.meeting_id, MeetingAttachment.deleted_at.is_(None))",
        lazy="noload",
        viewonly=True,
    )
    video_embeds: Mapped[list["MeetingVideoEmbed"]] = relationship(  # noqa: F821
        primaryjoin="and_(Meeting.id == MeetingVideoEmbed.meeting_id, MeetingVideoEmbed.deleted_at.is_(None))",
        lazy="noload",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint(
            "meeting_type IN ('regular', 'special', 'work_session', 'emergency', 'public_hearing')",
            name="ck_meeting_type",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled', 'postponed')",
            name="ck_meeting_status",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_meeting_approval_status",
        ),
        Index("ix_meetings_governing_body_id", "governing_body_id"),
        Index("ix_meetings_date", "meeting_date"),
        Index("ix_meetings_type_status", "meeting_type", "status"),
        Index("ix_meetings_approval_status", "approval_status"),
        Index("ix_meetings_submitted_by", "submitted_by"),
    )
