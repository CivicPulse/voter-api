"""Pydantic v2 schemas for boundary operations."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.county_metadata import CountyMetadataResponse


class BoundaryTypesResponse(BaseModel):
    """List of distinct boundary type strings."""

    types: list[str]


class BoundarySummaryResponse(BaseModel):
    """Boundary response without geometry (for list endpoints)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    boundary_type: str
    boundary_identifier: str
    source: str
    county: str | None = None
    effective_date: date | None = None
    created_at: datetime


class BoundaryDetailResponse(BoundarySummaryResponse):
    """Boundary response with GeoJSON geometry."""

    geometry: dict | None = None
    properties: dict | None = None
    county_metadata: CountyMetadataResponse | None = None


class PaginatedBoundaryResponse(BaseModel):
    """Paginated list of boundaries."""

    items: list[BoundarySummaryResponse]
    pagination: PaginationMeta


class ContainingPointRequest(BaseModel):
    """Query parameters for point-in-polygon lookup."""

    latitude: float
    longitude: float
    boundary_type: str | None = None


class BoundaryGeoJSONFeature(BaseModel):
    """A single GeoJSON Feature representing a boundary polygon."""

    type: str = "Feature"
    id: str
    geometry: dict
    properties: dict


class BoundaryFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection of boundary polygons."""

    type: str = "FeatureCollection"
    features: list[BoundaryGeoJSONFeature]
