"""AuditLog model for immutable data access tracking."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class AuditLog(Base, UUIDMixin):
    """Immutable record of data access events. Write-only (no updates or deletes)."""

    __tablename__ = "audit_logs"

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    request_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
