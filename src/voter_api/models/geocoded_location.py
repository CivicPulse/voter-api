"""GeocodedLocation model — stores geocoding results for voter addresses."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Double, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class GeocodedLocation(Base, UUIDMixin):
    """A single geocoding result for a voter's residence address from a specific source."""

    __tablename__ = "geocoded_locations"

    voter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Double, nullable=False)
    longitude: Mapped[float] = mapped_column(Double, nullable=False)
    point: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_address: Mapped[str | None] = mapped_column(String, nullable=True)
    geocoded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationship back to voter
    voter = relationship("Voter", back_populates="geocoded_locations", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("voter_id", "source_type", name="uq_voter_source"),
        Index("ix_geocoded_primary", "voter_id", postgresql_where="is_primary = true"),
    )
