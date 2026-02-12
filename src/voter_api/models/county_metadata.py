"""CountyMetadata model — Census TIGER/Line attributes for county boundaries.

Stores metadata from the US Census Bureau TIGER/Line county shapefile
(tl_2025_us_county.zip). Linked to the boundaries table via GEOID
(boundaries.boundary_identifier = county_metadata.geoid for county boundaries).

TIGER/Line column mapping:
    STATEFP  -> fips_state          CSAFP    -> csa_code
    COUNTYFP -> fips_county         CBSAFP   -> cbsa_code
    COUNTYNS -> gnis_code           METDIVFP -> metdiv_code
    GEOID    -> geoid               FUNCSTAT -> functional_status
    GEOIDFQ  -> geoid_fq            ALAND    -> land_area_m2
    NAME     -> name                AWATER   -> water_area_m2
    NAMELSAD -> name_lsad           INTPTLAT -> internal_point_lat
    LSAD     -> lsad_code           INTPTLON -> internal_point_lon
    CLASSFP  -> class_fp
    MTFCC    -> mtfcc
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from voter_api.models.base import Base, UUIDMixin


class CountyMetadata(Base, UUIDMixin):
    """Census TIGER/Line metadata for US county boundaries.

    Standalone reference table keyed by FIPS GEOID. Populated during
    county boundary import and designed for future enrichment with
    Census ACS demographic/population data.
    """

    __tablename__ = "county_metadata"

    # Primary identifiers
    geoid: Mapped[str] = mapped_column(String(5), nullable=False)
    fips_state: Mapped[str] = mapped_column(String(2), nullable=False)
    fips_county: Mapped[str] = mapped_column(String(3), nullable=False)
    gnis_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    geoid_fq: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Names
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    name_lsad: Mapped[str] = mapped_column(String(200), nullable=False)

    # Classification codes
    lsad_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    class_fp: Mapped[str | None] = mapped_column(String(2), nullable=True)
    mtfcc: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Statistical area codes
    csa_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    cbsa_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    metdiv_code: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Status and area
    functional_status: Mapped[str | None] = mapped_column(String(1), nullable=True)
    land_area_m2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    water_area_m2: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Internal point (Census-computed centroid)
    internal_point_lat: Mapped[str | None] = mapped_column(String(15), nullable=True)
    internal_point_lon: Mapped[str | None] = mapped_column(String(15), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("geoid", name="uq_county_metadata_geoid"),
        Index("ix_county_metadata_name", "name"),
        Index("ix_county_metadata_fips_state", "fips_state"),
    )
