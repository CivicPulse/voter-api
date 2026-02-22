"""Pydantic v2 schemas for governing body type operations."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class GoverningBodyTypeResponse(BaseModel):
    """A governing body type classification."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    is_default: bool
    created_at: datetime


class GoverningBodyTypeCreateRequest(BaseModel):
    """Request body for creating a governing body type."""

    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
