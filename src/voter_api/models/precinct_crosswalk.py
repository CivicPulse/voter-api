"""PrecinctCrosswalk ORM model — maps voter precinct codes to boundary identifiers."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class PrecinctCrosswalk(Base, UUIDMixin):
    """Maps voter-file precinct codes to boundary precinct identifiers.

    Voter files use county-specific precinct codes that don't match the
    boundary/shapefile precinct identifiers. This crosswalk enables joining
    voter data to precinct geometries.
    """

    __tablename__ = "precinct_crosswalk"

    county_code: Mapped[str] = mapped_column(String(10), nullable=False)
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    voter_precinct_code: Mapped[str] = mapped_column(String(50), nullable=False)
    boundary_precinct_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, server_default="spatial_join")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("county_name", "voter_precinct_code", name="uq_precinct_crosswalk_county_precinct"),
    )
