"""Pydantic v2 schemas for video embed operations."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VideoPlatformEnum(enum.StrEnum):
    """Supported video hosting platforms."""

    YOUTUBE = "youtube"
    VIMEO = "vimeo"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class VideoEmbedResponse(BaseModel):
    """Video embed response."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    agenda_item_id: uuid.UUID | None = None
    video_url: str
    platform: VideoPlatformEnum
    start_seconds: int | None = None
    end_seconds: int | None = None
    created_at: datetime


class VideoEmbedListResponse(BaseModel):
    """List of video embeds."""

    items: list[VideoEmbedResponse]


# ---------------------------------------------------------------------------
# Write schemas
# ---------------------------------------------------------------------------


class VideoEmbedCreateRequest(BaseModel):
    """Request body for creating a video embed."""

    video_url: str = Field(min_length=1, max_length=1000)
    start_seconds: int | None = Field(default=None, ge=0)
    end_seconds: int | None = Field(default=None, ge=0)


class VideoEmbedUpdateRequest(BaseModel):
    """Request body for updating a video embed. All fields optional."""

    video_url: str | None = Field(default=None, min_length=1, max_length=1000)
    start_seconds: int | None = Field(default=None, ge=0)
    end_seconds: int | None = Field(default=None, ge=0)
