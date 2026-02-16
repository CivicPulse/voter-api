"""PrecinctMetadata model — GA SoS precinct shapefile attributes.

Stores typed metadata from the Georgia Secretary of State county precinct
shapefile (gaprec_2024-website-shapefile.zip). Linked to the boundaries
table via FK on boundary_id.

Shapefile column mapping:
    DISTRICT   -> sos_district_id    CONTY      -> county_number
    CTYSOSID   -> sos_id             PRECINCT_I -> precinct_id
    FIPS       -> fips               PRECINCT_N -> precinct_name
    FIPS2      -> fips_county        AREA       -> area
    CTYNAME    -> county_name
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class PrecinctMetadata(Base, UUIDMixin):
    """GA Secretary of State metadata for county precinct boundaries.

    Stores typed fields extracted from the precinct shapefile properties.
    Each record is 1:1 with a county_precinct boundary row.
    """

    __tablename__ = "precinct_metadata"

    boundary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("boundaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    sos_district_id: Mapped[str] = mapped_column(String(10), nullable=False)
    sos_id: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fips: Mapped[str] = mapped_column(String(5), nullable=False)
    fips_county: Mapped[str] = mapped_column(String(3), nullable=False)
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    county_number: Mapped[str | None] = mapped_column(String(5), nullable=True)
    precinct_id: Mapped[str] = mapped_column(String(20), nullable=False)
    precinct_name: Mapped[str] = mapped_column(String(200), nullable=False)
    area: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("boundary_id", name="uq_precinct_metadata_boundary"),
        Index("ix_precinct_metadata_county_name", "county_name"),
        Index("ix_precinct_metadata_fips", "fips"),
        Index("ix_precinct_metadata_sos_district_id", "sos_district_id"),
        Index("ix_precinct_metadata_county_sos_id", "county_name", "sos_id"),
    )
