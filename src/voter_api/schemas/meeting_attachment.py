"""Pydantic v2 schemas for meeting attachment operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    """Attachment metadata response."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    meeting_id: uuid.UUID | None = None
    agenda_item_id: uuid.UUID | None = None
    original_filename: str
    file_size: int
    content_type: str
    download_url: str | None = None
    created_at: datetime


class AttachmentListResponse(BaseModel):
    """List of attachments."""

    items: list[AttachmentResponse]
