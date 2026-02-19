"""VoterHistory ORM model — stores individual voter participation records."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class VoterHistory(Base, UUIDMixin):
    """A single voter's participation in a single election.

    Records are imported from GA SoS voter history CSV files. The voter
    association is lazy — records join to voters by registration number
    at query time rather than via a foreign key.
    """

    __tablename__ = "voter_history"

    voter_registration_number: Mapped[str] = mapped_column(String(20), nullable=False)
    county: Mapped[str] = mapped_column(String(100), nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    election_type: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_election_type: Mapped[str] = mapped_column(String(20), nullable=False)
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ballot_style: Mapped[str | None] = mapped_column(String(100), nullable=True)
    absentee: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    provisional: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    supplemental: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    import_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "voter_registration_number",
            "election_date",
            "election_type",
            name="uq_voter_history_participation",
        ),
        Index("idx_voter_history_reg_num", "voter_registration_number"),
        Index("idx_voter_history_election_date", "election_date"),
        Index("idx_voter_history_election_type", "election_type"),
        Index("idx_voter_history_county", "county"),
        Index("idx_voter_history_import_job_id", "import_job_id"),
        Index("idx_voter_history_date_type", "election_date", "normalized_election_type"),
    )
