"""Candidacy ORM model — candidate-election junction table.

Links a candidate (person entity) to a specific election contest.
Contest-specific fields (party, filing_status, ballot_order, etc.)
live here; person-level fields live on the Candidate model.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from voter_api.models.candidate import Candidate
    from voter_api.models.election import Election
    from voter_api.models.import_job import ImportJob


class Candidacy(Base, UUIDMixin, TimestampMixin):
    """A candidacy record linking a candidate (person) to an election contest.

    Stores contest-specific data such as party, filing status, ballot order,
    and incumbent status. A candidate may have multiple candidacies across
    different elections.
    """

    __tablename__ = "candidacies"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    election_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("elections.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Contest-specific fields
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)
    filing_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="qualified")
    ballot_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_incumbent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    contest_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qualified_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    home_county: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sos_ballot_option_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Import tracking
    import_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    candidate: Mapped["Candidate"] = relationship(back_populates="candidacies")
    election: Mapped["Election"] = relationship(back_populates="candidacies")
    import_job: Mapped["ImportJob | None"] = relationship("ImportJob", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("candidate_id", "election_id", name="uq_candidacy_candidate_election"),
        CheckConstraint(
            "filing_status IN ('qualified', 'withdrawn', 'disqualified', 'write_in')",
            name="ck_candidacy_filing_status",
        ),
        Index("ix_candidacies_candidate_id", "candidate_id"),
        Index("ix_candidacies_election_id", "election_id"),
        Index("ix_candidacies_filing_status", "filing_status"),
        Index("ix_candidacies_home_county", "home_county"),
    )
