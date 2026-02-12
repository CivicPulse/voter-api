"""Pydantic v2 schemas for county metadata responses."""

from pydantic import BaseModel, computed_field


class CountyMetadataResponse(BaseModel):
    """Census TIGER/Line metadata for a county boundary."""

    model_config = {"from_attributes": True}

    geoid: str
    fips_state: str
    fips_county: str
    gnis_code: str | None = None
    geoid_fq: str | None = None
    name: str
    name_lsad: str
    lsad_code: str | None = None
    class_fp: str | None = None
    mtfcc: str | None = None
    csa_code: str | None = None
    cbsa_code: str | None = None
    metdiv_code: str | None = None
    functional_status: str | None = None
    land_area_m2: int | None = None
    water_area_m2: int | None = None
    internal_point_lat: str | None = None
    internal_point_lon: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def land_area_km2(self) -> float | None:
        """Land area in square kilometers."""
        if self.land_area_m2 is not None:
            return round(self.land_area_m2 / 1_000_000, 2)
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def water_area_km2(self) -> float | None:
        """Water area in square kilometers."""
        if self.water_area_m2 is not None:
            return round(self.water_area_m2 / 1_000_000, 2)
        return None
