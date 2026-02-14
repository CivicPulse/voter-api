"""Pydantic v2 schemas for elected official operations."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta

# ---------------------------------------------------------------------------
# Source schemas
# ---------------------------------------------------------------------------


class ElectedOfficialSourceResponse(BaseModel):
    """A cached data-provider record for an elected official."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    source_name: str
    source_record_id: str
    boundary_type: str
    district_identifier: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    party: str | None = None
    title: str | None = None
    photo_url: str | None = None
    term_start_date: date | None = None
    term_end_date: date | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    office_address: str | None = None
    fetched_at: datetime
    is_current: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Official schemas
# ---------------------------------------------------------------------------


class ElectedOfficialSummaryResponse(BaseModel):
    """Elected official summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    boundary_type: str
    district_identifier: str
    full_name: str
    party: str | None = None
    title: str | None = None
    photo_url: str | None = None
    status: str
    created_at: datetime


class ElectedOfficialDetailResponse(ElectedOfficialSummaryResponse):
    """Full elected official detail with contact info and sources."""

    first_name: str | None = None
    last_name: str | None = None

    term_start_date: date | None = None
    term_end_date: date | None = None
    last_election_date: date | None = None
    next_election_date: date | None = None

    website: str | None = None
    email: str | None = None
    phone: str | None = None
    office_address: str | None = None

    external_ids: dict | None = None

    approved_by_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    updated_at: datetime

    sources: list[ElectedOfficialSourceResponse] = Field(default_factory=list)


class PaginatedElectedOfficialResponse(BaseModel):
    """Paginated list of elected officials."""

    items: list[ElectedOfficialSummaryResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Write schemas (admin)
# ---------------------------------------------------------------------------


class ElectedOfficialCreateRequest(BaseModel):
    """Request body for creating an elected official record."""

    boundary_type: str
    district_identifier: str
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    party: str | None = None
    title: str | None = None
    photo_url: str | None = None

    term_start_date: date | None = None
    term_end_date: date | None = None
    last_election_date: date | None = None
    next_election_date: date | None = None

    website: str | None = None
    email: str | None = None
    phone: str | None = None
    office_address: str | None = None

    external_ids: dict | None = None


class ElectedOfficialUpdateRequest(BaseModel):
    """Request body for updating an elected official record.

    All fields optional — only provided fields are updated.
    """

    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    party: str | None = None
    title: str | None = None
    photo_url: str | None = None

    term_start_date: date | None = None
    term_end_date: date | None = None
    last_election_date: date | None = None
    next_election_date: date | None = None

    website: str | None = None
    email: str | None = None
    phone: str | None = None
    office_address: str | None = None

    external_ids: dict | None = None


class ApproveOfficialRequest(BaseModel):
    """Request body for approving (or overriding) an elected official record.

    Optionally supply a source_id to promote a specific source's data
    into the canonical record.
    """

    source_id: uuid.UUID | None = Field(
        default=None, description="Source record to promote. Omit to approve current data as-is."
    )
