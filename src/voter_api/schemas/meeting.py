"""Pydantic v2 schemas for meeting operations."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class MeetingTypeEnum(enum.StrEnum):
    """Meeting type classification."""

    REGULAR = "regular"
    SPECIAL = "special"
    WORK_SESSION = "work_session"
    EMERGENCY = "emergency"
    PUBLIC_HEARING = "public_hearing"


class MeetingStatusEnum(enum.StrEnum):
    """Meeting lifecycle status."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"


class ApprovalStatusEnum(enum.StrEnum):
    """Approval workflow status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class MeetingSummaryResponse(BaseModel):
    """Meeting summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    governing_body_id: uuid.UUID
    governing_body_name: str | None = None
    meeting_date: datetime
    location: str | None = None
    meeting_type: MeetingTypeEnum
    status: MeetingStatusEnum
    approval_status: ApprovalStatusEnum
    external_source_url: str | None = None
    created_at: datetime


class MeetingDetailResponse(MeetingSummaryResponse):
    """Full meeting detail with child counts and approval fields."""

    submitted_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    agenda_item_count: int = 0
    attachment_count: int = 0
    video_embed_count: int = 0
    updated_at: datetime


class PaginatedMeetingResponse(BaseModel):
    """Paginated list of meetings."""

    items: list[MeetingSummaryResponse]
    pagination: PaginationMeta


# ---------------------------------------------------------------------------
# Write schemas
# ---------------------------------------------------------------------------


class MeetingCreateRequest(BaseModel):
    """Request body for creating a meeting."""

    governing_body_id: uuid.UUID
    meeting_date: datetime
    location: str | None = Field(default=None, max_length=500)
    meeting_type: MeetingTypeEnum
    status: MeetingStatusEnum
    external_source_url: str | None = Field(default=None, max_length=1000)


class MeetingUpdateRequest(BaseModel):
    """Request body for updating a meeting. All fields optional."""

    meeting_date: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    meeting_type: MeetingTypeEnum | None = None
    status: MeetingStatusEnum | None = None
    external_source_url: str | None = Field(default=None, max_length=1000)


class MeetingRejectRequest(BaseModel):
    """Request body for rejecting a meeting."""

    reason: str = Field(min_length=1)
