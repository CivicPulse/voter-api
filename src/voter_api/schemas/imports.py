"""Import job Pydantic v2 request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class ImportJobResponse(BaseModel):
    """Import job status and metadata."""

    id: UUID
    file_name: str
    file_type: str
    status: str
    total_records: int | None = None
    records_succeeded: int | None = None
    records_failed: int | None = None
    records_inserted: int | None = None
    records_updated: int | None = None
    records_soft_deleted: int | None = None
    records_skipped: int | None = None
    records_unmatched: int | None = None
    error_log: dict | None = None
    triggered_by: UUID | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedImportJobResponse(BaseModel):
    """Paginated list of import jobs."""

    items: list[ImportJobResponse]
    pagination: PaginationMeta


class ImportDiffResponse(BaseModel):
    """Import diff report showing changes."""

    job_id: UUID
    added: list[str] = Field(default_factory=list, description="Voter registration numbers added")
    removed: list[str] = Field(default_factory=list, description="Voter registration numbers removed (soft-deleted)")
    updated: list[str] = Field(default_factory=list, description="Voter registration numbers updated")
