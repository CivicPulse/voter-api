"""Export Pydantic v2 request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class ExportFilters(BaseModel):
    """Filter criteria for export requests."""

    county: str | None = None
    status: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    residence_city: str | None = None
    residence_zipcode: str | None = None
    congressional_district: str | None = None
    state_senate_district: str | None = None
    state_house_district: str | None = None
    county_precinct: str | None = None
    analysis_run_id: UUID | None = None
    match_status: str | None = None
    present_in_latest_import: bool | None = None


class ExportRequest(BaseModel):
    """Request to create a bulk data export."""

    output_format: str = Field(..., pattern=r"^(csv|json|geojson)$")
    filters: ExportFilters = Field(default_factory=ExportFilters)


class ExportJobResponse(BaseModel):
    """Response for an export job."""

    id: UUID
    output_format: str
    filters: dict
    status: str
    record_count: int | None = None
    file_size_bytes: int | None = None
    requested_at: datetime
    completed_at: datetime | None = None
    download_url: str | None = None

    model_config = {"from_attributes": True}


class PaginatedExportJobResponse(BaseModel):
    """Paginated list of export jobs."""

    items: list[ExportJobResponse]
    pagination: PaginationMeta
