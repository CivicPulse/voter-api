"""Pydantic v2 schemas for meeting full-text search."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.meeting import MeetingTypeEnum


class MatchSourceEnum(enum.StrEnum):
    """Where the search match was found."""

    AGENDA_ITEM = "agenda_item"
    ATTACHMENT_FILENAME = "attachment_filename"


class SearchResultItem(BaseModel):
    """A single search result with meeting context."""

    agenda_item_id: uuid.UUID | None = None
    title: str
    description_excerpt: str | None = None
    meeting_id: uuid.UUID
    meeting_date: datetime
    meeting_type: MeetingTypeEnum
    governing_body_id: uuid.UUID
    governing_body_name: str
    match_source: MatchSourceEnum
    relevance_score: float = 0.0


class PaginatedSearchResultResponse(BaseModel):
    """Paginated search results."""

    items: list[SearchResultItem]
    pagination: PaginationMeta
