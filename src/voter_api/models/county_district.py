"""CountyDistrict model — maps counties to their legislative/congressional districts."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class CountyDistrict(Base, UUIDMixin):
    """Many-to-many mapping between counties and district boundaries.

    Populated from the state-provided county-to-district CSV data.
    Used to resolve which multi-county districts (congressional, state_senate,
    state_house) intersect a given county without relying on centroid-based
    spatial queries.
    """

    __tablename__ = "county_districts"

    county_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    boundary_type: Mapped[str] = mapped_column(String(50), nullable=False)
    district_identifier: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("county_name", "boundary_type", "district_identifier", name="uq_county_district"),
        Index("ix_county_districts_type_identifier", "boundary_type", "district_identifier"),
    )
