"""ExportJob model — tracks a bulk data export operation."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class ExportJob(Base, UUIDMixin):
    """Tracks a bulk data export operation.

    Stores filter criteria, output format, file path, and progress status.
    """

    __tablename__ = "export_jobs"

    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_export_status", "status"),
        Index("ix_export_triggered_by", "triggered_by"),
    )
