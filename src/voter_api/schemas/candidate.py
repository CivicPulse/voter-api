"""Pydantic v2 schemas for candidate endpoints.

Request/response models per specs/010-election-info/contracts/openapi.yaml.
"""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class FilingStatus(enum.StrEnum):
    """Candidate filing status lifecycle."""

    QUALIFIED = "qualified"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"
    WRITE_IN = "write_in"


class LinkType(enum.StrEnum):
    """Allowed candidate link types."""

    WEBSITE = "website"
    CAMPAIGN = "campaign"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    OTHER = "other"


# --- Link schemas ---


class CandidateLinkCreateRequest(BaseModel):
    """Request body for creating a candidate link."""

    link_type: LinkType
    url: str = Field(min_length=1)
    label: str | None = Field(default=None, max_length=200)


class CandidateLinkResponse(BaseModel):
    """Response for a candidate link."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    link_type: str
    url: str
    label: str | None = None


# --- Candidate schemas ---


class CandidateCreateRequest(BaseModel):
    """Request body for creating a candidate."""

    full_name: str = Field(min_length=1, max_length=200)
    party: str | None = Field(default=None, max_length=50)
    bio: str | None = None
    photo_url: str | None = None
    ballot_order: int | None = None
    filing_status: FilingStatus = FilingStatus.QUALIFIED
    is_incumbent: bool = False
    sos_ballot_option_id: str | None = Field(default=None, max_length=50)
    links: list[CandidateLinkCreateRequest] = Field(default_factory=list)


class CandidateUpdateRequest(BaseModel):
    """Request body for updating a candidate (partial PATCH).

    All fields are optional. ``full_name`` is typed as ``str`` (not
    ``str | None``) so that sending it explicitly sets the value but
    omitting it leaves the column unchanged. This prevents accidentally
    setting a NOT NULL column to null.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    party: str | None = None
    bio: str | None = None
    photo_url: str | None = None
    ballot_order: int | None = None
    filing_status: FilingStatus | None = None
    is_incumbent: bool | None = None
    sos_ballot_option_id: str | None = None


class CandidateSummaryResponse(BaseModel):
    """Candidate summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    election_id: uuid.UUID
    full_name: str
    party: str | None = None
    photo_url: str | None = None
    ballot_order: int | None = None
    filing_status: str
    is_incumbent: bool
    created_at: datetime


class CandidateDetailResponse(CandidateSummaryResponse):
    """Full candidate detail response with links and optional SOS results."""

    bio: str | None = None
    sos_ballot_option_id: str | None = None
    updated_at: datetime
    links: list[CandidateLinkResponse] = Field(default_factory=list)
    result_vote_count: int | None = None
    result_political_party: str | None = None


class PaginatedCandidateResponse(BaseModel):
    """Paginated list of candidates."""

    items: list[CandidateSummaryResponse]
    pagination: PaginationMeta
