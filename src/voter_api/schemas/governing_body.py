"""Pydantic v2 schemas for governing body operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.governing_body_type import GoverningBodyTypeResponse

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class GoverningBodySummaryResponse(BaseModel):
    """Governing body summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    type: GoverningBodyTypeResponse
    jurisdiction: str
    website_url: str | None = None
    created_at: datetime


class GoverningBodyDetailResponse(GoverningBodySummaryResponse):
    """Full governing body detail with meeting count."""

    description: str | None = None
    meeting_count: int = 0
    updated_at: datetime


class PaginatedGoverningBodyResponse(BaseModel):
    """Paginated list of governing bodies."""

    items: list[GoverningBodySummaryResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Write schemas (admin)
# ---------------------------------------------------------------------------


class GoverningBodyCreateRequest(BaseModel):
    """Request body for creating a governing body."""

    name: str = Field(min_length=1, max_length=200)
    type_id: uuid.UUID
    jurisdiction: str = Field(min_length=1, max_length=200)
    description: str | None = None
    website_url: HttpUrl | None = None


class GoverningBodyUpdateRequest(BaseModel):
    """Request body for updating a governing body.

    All fields optional -- only provided fields are updated.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    type_id: uuid.UUID | None = None
    jurisdiction: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    website_url: HttpUrl | None = None
