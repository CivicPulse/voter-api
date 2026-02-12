"""Pydantic v2 schemas for precinct metadata responses."""

from decimal import Decimal

from pydantic import BaseModel


class PrecinctMetadataResponse(BaseModel):
    """GA Secretary of State metadata for a county precinct boundary."""

    model_config = {"from_attributes": True}

    sos_district_id: str
    sos_id: str | None = None
    fips: str
    fips_county: str
    county_name: str
    county_number: str | None = None
    precinct_id: str
    precinct_name: str
    area: Decimal | None = None
