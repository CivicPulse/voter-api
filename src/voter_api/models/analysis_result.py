"""AnalysisResult model — outcome of comparing a voter's location to registration."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class AnalysisResult(Base, UUIDMixin):
    """Outcome of comparing a voter's physical location to their registration.

    Immutable once the parent AnalysisRun completes. Stores both the
    spatially-determined boundaries and the registered boundaries for
    comparison, along with the match classification.
    """

    __tablename__ = "analysis_results"

    analysis_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    determined_boundaries: Mapped[dict] = mapped_column(JSONB, nullable=False)
    registered_boundaries: Mapped[dict] = mapped_column(JSONB, nullable=False)
    match_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    mismatch_details: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    analysis_run = relationship("AnalysisRun", back_populates="results", lazy="selectin")
    voter = relationship("Voter", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("analysis_run_id", "voter_id", name="ix_result_run_voter"),
        Index("ix_result_run_id", "analysis_run_id"),
        Index("ix_result_voter_id", "voter_id"),
        Index("ix_result_match_status", "match_status"),
    )
