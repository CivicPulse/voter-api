"""ElectedOfficial model — canonical elected official records.

Stores the authoritative representation of elected officials that the API
serves. Each record represents a person currently holding or recently holding
office for a specific district/seat. Linked to boundaries via
(boundary_type, district_identifier) rather than FK, since officials may be
entered before boundary geometries are imported.

Admin approval workflow:
    auto     — populated from automated source, not yet reviewed
    approved — admin has verified the automated data
    manual   — admin manually entered or overrode the record
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin


class ElectedOfficial(Base, UUIDMixin):
    """Canonical elected official record served by the API.

    Represents the admin-approved (or auto-populated) view of who holds
    a given office. One record per seat/district at a time.
    """

    __tablename__ = "elected_officials"

    # District linkage (matches Boundary.boundary_type + boundary_identifier)
    boundary_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    district_identifier: Mapped[str] = mapped_column(String(50), nullable=False)

    # Person
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Term / election dates
    term_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    term_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_election_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_election_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Contact
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    office_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # External identifiers for cross-referencing (bioguide_id, open_states_id, etc.)
    external_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Admin approval workflow
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sources: Mapped[list["ElectedOfficialSource"]] = relationship(
        back_populates="elected_official", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        UniqueConstraint("boundary_type", "district_identifier", "full_name", name="uq_official_district_name"),
        Index("ix_elected_officials_district", "boundary_type", "district_identifier"),
        Index("ix_elected_officials_name", "last_name", "first_name"),
    )


class ElectedOfficialSource(Base, UUIDMixin):
    """Cached response from an external data provider.

    Each row represents a single provider's view of an elected official
    for a given district. Multiple sources may exist for the same seat.
    Admins compare sources to determine the canonical record.
    """

    __tablename__ = "elected_official_sources"

    # Link to canonical record (nullable until matched)
    elected_official_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("elected_officials.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Source identification
    source_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(200), nullable=False)

    # District context (denormalized for querying unmatched sources)
    boundary_type: Mapped[str] = mapped_column(String(50), nullable=False)
    district_identifier: Mapped[str] = mapped_column(String(50), nullable=False)

    # Raw cached response from the provider
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Normalized fields parsed from raw_data
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    party: Mapped[str | None] = mapped_column(String(50), nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Term / election dates (if available from source)
    term_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    term_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Contact (if available from source)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    office_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tracking
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    elected_official: Mapped["ElectedOfficial | None"] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("source_name", "source_record_id", name="uq_source_record"),
        Index("ix_source_district", "boundary_type", "district_identifier"),
    )
