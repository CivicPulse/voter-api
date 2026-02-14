"""GeocodingJob model — tracks batch geocoding operations."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class GeocodingJob(Base, UUIDMixin):
    """Tracks a batch geocoding operation for progress and checkpoint/resume."""

    __tablename__ = "geocoding_jobs"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    county: Mapped[str | None] = mapped_column(String(100), nullable=True)
    force_regeocode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )

    # Progress counts
    total_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    succeeded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hits: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Checkpoint for resume (SC-009)
    last_processed_voter_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error tracking
    error_log: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Metadata
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
