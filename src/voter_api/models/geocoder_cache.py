"""GeocoderCache model — caches geocoding responses per provider and normalized address."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Double, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class GeocoderCache(Base, UUIDMixin):
    """Cached geocoding result keyed by provider and normalized address."""

    __tablename__ = "geocoder_cache"

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_address: Mapped[str] = mapped_column(String, nullable=False)
    latitude: Mapped[float] = mapped_column(Double, nullable=False)
    longitude: Mapped[float] = mapped_column(Double, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # FK to canonical address store (nullable for backward compatibility)
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True, index=True
    )

    # Relationships
    address = relationship("Address", back_populates="geocoder_cache_entries")

    __table_args__ = (UniqueConstraint("provider", "normalized_address", name="uq_provider_address"),)
