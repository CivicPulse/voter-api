"""GeocoderCache model — caches geocoding responses per provider and normalized address."""

from datetime import datetime

from sqlalchemy import DateTime, Double, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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

    __table_args__ = (UniqueConstraint("provider", "normalized_address", name="uq_provider_address"),)
