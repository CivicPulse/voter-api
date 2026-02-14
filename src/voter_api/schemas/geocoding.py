"""Pydantic v2 schemas for geocoding operations."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GeocodedLocationResponse(BaseModel):
    """Response schema for a geocoded location."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    voter_id: uuid.UUID
    latitude: float
    longitude: float
    confidence_score: float | None = None
    source_type: str
    is_primary: bool
    input_address: str | None = None
    geocoded_at: datetime


class ManualGeocodingRequest(BaseModel):
    """Request to manually add a geocoded location for a voter."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    source_type: str = Field(..., pattern="^(manual|field-survey)$", description="manual or field-survey")
    set_as_primary: bool = False


class BatchGeocodingRequest(BaseModel):
    """Request to trigger a batch geocoding job."""

    county: str | None = None
    provider: Literal["census"] = "census"
    force_regeocode: bool = False


class GeocodingJobResponse(BaseModel):
    """Response schema for a geocoding job."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    provider: str
    county: str | None = None
    force_regeocode: bool
    status: str
    total_records: int | None = None
    processed: int | None = None
    succeeded: int | None = None
    failed: int | None = None
    cache_hits: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class CacheProviderStats(BaseModel):
    """Per-provider cache statistics."""

    provider: str
    cached_count: int
    oldest_entry: datetime | None = None
    newest_entry: datetime | None = None


class CacheStatsResponse(BaseModel):
    """Response for geocoding cache statistics."""

    providers: list[CacheProviderStats]


# --- Single-address geocoding endpoint schemas ---


class GeocodeMetadata(BaseModel):
    """Metadata for a geocode response."""

    cached: bool
    provider: str

    model_config = {"extra": "allow"}


class AddressGeocodeResponse(BaseModel):
    """Response for GET /geocoding/geocode."""

    formatted_address: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    confidence: float | None = None
    metadata: GeocodeMetadata


class MalformedComponent(BaseModel):
    """A component detected but improperly formatted."""

    component: str
    issue: str


class ValidationDetail(BaseModel):
    """Address component validation feedback."""

    present_components: list[str]
    missing_components: list[str]
    malformed_components: list[MalformedComponent] = Field(default_factory=list)


class AddressSuggestion(BaseModel):
    """A ranked address suggestion from the canonical store."""

    address: str
    latitude: float
    longitude: float
    confidence_score: float | None = None


class AddressVerifyResponse(BaseModel):
    """Response for GET /geocoding/verify."""

    input_address: str
    normalized_address: str
    is_well_formed: bool
    validation: ValidationDetail
    suggestions: list[AddressSuggestion] = Field(default_factory=list)


class DistrictInfo(BaseModel):
    """A boundary district containing a queried point."""

    boundary_type: str
    name: str
    boundary_identifier: str
    boundary_id: uuid.UUID
    metadata: dict = Field(default_factory=dict)


class PointLookupResponse(BaseModel):
    """Response for GET /geocoding/point-lookup."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: float | None = None
    districts: list[DistrictInfo] = Field(default_factory=list)
