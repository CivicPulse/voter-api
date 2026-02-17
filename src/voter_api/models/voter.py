"""Voter model — central entity sourced from Georgia Secretary of State voter file."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, TimestampMixin, UUIDMixin


class Voter(Base, UUIDMixin, TimestampMixin):
    """Individual voter record from the GA Secretary of State voter file."""

    __tablename__ = "voters"

    # Core identification
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    voter_registration_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Name fields
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Demographics
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Residence address
    residence_street_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    residence_pre_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residence_street_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    residence_street_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    residence_post_direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residence_apt_unit_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    residence_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    residence_zipcode: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)

    # Mailing address
    mailing_street_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mailing_street_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_apt_unit_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    mailing_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mailing_zipcode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    mailing_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mailing_country: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Registered districts
    county_precinct: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    county_precinct_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    municipal_precinct: Mapped[str | None] = mapped_column(String(20), nullable=True)
    municipal_precinct_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    congressional_district: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    state_senate_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    state_house_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    judicial_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    county_commission_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    school_board_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    city_council_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    municipal_school_board_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    water_board_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    super_council_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    super_commissioner_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    super_school_board_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fire_district: Mapped[str | None] = mapped_column(String(10), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    combo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    land_lot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    land_district: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Dates
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_modified_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_of_last_contact: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_vote_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    voter_created_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_party_voted: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Soft-delete tracking
    present_in_latest_import: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true", index=True
    )
    soft_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Import tracking FKs
    last_seen_in_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    first_seen_in_import_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # FK to canonical address store (nullable — set during post-import processing)
    residence_address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True, index=True
    )

    # Relationships
    geocoded_locations = relationship("GeocodedLocation", back_populates="voter", lazy="selectin")
    residence_address = relationship("Address", back_populates="voters")

    __table_args__ = (Index("ix_voters_name_search", "last_name", "first_name"),)
