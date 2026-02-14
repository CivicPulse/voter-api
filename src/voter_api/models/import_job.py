"""ImportJob model — tracks data import operations."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class ImportJob(Base, UUIDMixin):
    """Tracks a data import operation (voter file or boundary file)."""

    __tablename__ = "import_jobs"

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending", index=True
    )

    # Record counts
    total_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_succeeded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_inserted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_updated: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_soft_deleted: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error tracking
    error_log: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    # Checkpoint for resume
    last_processed_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metadata
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
