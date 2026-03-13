"""Candidate and CandidateLink ORM models.

Stores candidates running in elections and their associated external links.
Candidates are admin-managed records that exist independently of SOS results.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from voter_api.models.election import Election
    from voter_api.models.import_job import ImportJob


class Candidate(Base, UUIDMixin, TimestampMixin):
    """A person running for office in a specific election.

    Candidates are created from local Board of Elections publications,
    qualifying lists, or sample ballots. They exist independently of SOS
    results and can be entered weeks or months before election day.
    """

    __tablename__ = "candidates"

    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elections.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ballot_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="qualified")
    is_incumbent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sos_ballot_option_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Import fields (populated by candidate importer)
    contest_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qualified_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    home_county: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    election: Mapped["Election"] = relationship(back_populates="candidates")
    import_job: Mapped["ImportJob | None"] = relationship("ImportJob", lazy="selectin")
    links: Mapped[list["CandidateLink"]] = relationship(
        back_populates="candidate",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("election_id", "full_name", name="uq_candidate_election_name"),
        CheckConstraint(
            "filing_status IN ('qualified', 'withdrawn', 'disqualified', 'write_in')",
            name="ck_candidate_filing_status",
        ),
        Index("ix_candidates_election_id", "election_id"),
        Index("ix_candidates_filing_status", "filing_status"),
        Index("ix_candidates_home_county", "home_county"),
    )


class CandidateLink(Base, UUIDMixin):
    """Typed external URL entry associated with a candidate.

    Supports multiple links per candidate with predefined types for
    common social media and web properties.
    """

    __tablename__ = "candidate_links"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship(back_populates="links")

    __table_args__ = (
        CheckConstraint(
            "link_type IN ('website', 'campaign', 'facebook', 'twitter', 'instagram', 'youtube', 'linkedin', 'other')",
            name="ck_candidate_link_type",
        ),
        Index("ix_candidate_links_candidate_id", "candidate_id"),
    )
