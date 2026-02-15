"""Boundary model — political/administrative district and precinct boundaries."""

from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin

# Valid boundary types matching GA SoS district types
BOUNDARY_TYPES = [
    "congressional",
    "state_senate",
    "state_house",
    "judicial",
    "psc",
    "county",
    "county_commission",
    "school_board",
    "city_council",
    "municipal_school_board",
    "water_board",
    "super_council",
    "super_commissioner",
    "super_school_board",
    "fire_district",
    "county_precinct",
    "municipal_precinct",
    "us_senate",
]


class Boundary(Base, UUIDMixin):
    """Political or administrative district/precinct boundary polygon."""

    __tablename__ = "boundaries"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    boundary_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    boundary_identifier: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    county: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    geometry: Mapped[Any] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=False,
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("boundary_type", "boundary_identifier", "county", name="uq_boundary_type_id_county"),
        Index("idx_boundaries_geometry", "geometry", postgresql_using="gist"),
    )
