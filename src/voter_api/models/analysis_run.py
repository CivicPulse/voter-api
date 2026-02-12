"""AnalysisRun model — tracks a single execution of location analysis."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class AnalysisRun(Base, UUIDMixin):
    """A single execution of the location analysis process.

    Each run produces a complete snapshot of results comparing
    voter geocoded locations against boundary data.
    """

    __tablename__ = "analysis_runs"

    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    total_voters_analyzed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mismatch_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unable_to_analyze_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_processed_voter_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    results = relationship("AnalysisResult", back_populates="analysis_run", lazy="dynamic")

    __table_args__ = (
        Index("ix_analysis_run_status", "status"),
        Index("ix_analysis_run_created_at", "created_at"),
    )
