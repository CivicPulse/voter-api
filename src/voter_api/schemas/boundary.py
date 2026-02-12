"""Pydantic v2 schemas for boundary operations."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from voter_api.schemas.common import PaginationMeta


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


class PaginatedBoundaryResponse(BaseModel):
    """Paginated list of boundaries."""

    items: list[BoundarySummaryResponse]
    pagination: PaginationMeta


class ContainingPointRequest(BaseModel):
    """Query parameters for point-in-polygon lookup."""

    latitude: float
    longitude: float
    boundary_type: str | None = None
