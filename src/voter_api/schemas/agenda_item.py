"""Pydantic v2 schemas for agenda item operations."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DispositionEnum(enum.StrEnum):
    """Possible outcomes for an agenda item."""

    APPROVED = "approved"
    DENIED = "denied"
    TABLED = "tabled"
    NO_ACTION = "no_action"
    INFORMATIONAL = "informational"


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AgendaItemResponse(BaseModel):
    """Agenda item response with child counts."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    meeting_id: uuid.UUID
    title: str
    description: str | None = None
    action_taken: str | None = None
    disposition: DispositionEnum | None = None
    display_order: int
    attachment_count: int = 0
    video_embed_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgendaItemListResponse(BaseModel):
    """List of agenda items (no pagination — returned in order)."""

    items: list[AgendaItemResponse]


# ---------------------------------------------------------------------------
# Write schemas
# ---------------------------------------------------------------------------


class AgendaItemCreateRequest(BaseModel):
    """Request body for creating an agenda item."""

    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    action_taken: str | None = None
    disposition: DispositionEnum | None = None
    display_order: int | None = Field(
        default=None, ge=0, description="Position in the agenda. If omitted, appended to end."
    )


class AgendaItemUpdateRequest(BaseModel):
    """Request body for updating an agenda item. All fields optional."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    action_taken: str | None = None
    disposition: DispositionEnum | None = None


class AgendaItemReorderRequest(BaseModel):
    """Request body for bulk reordering agenda items."""

    item_ids: list[uuid.UUID] = Field(
        min_length=1, description="Ordered list of agenda item IDs defining the new order"
    )
