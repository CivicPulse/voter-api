"""Analysis Pydantic v2 request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter import VoterSummaryResponse


class TriggerAnalysisRequest(BaseModel):
    """Request to trigger a new analysis run."""

    county: str | None = None
    notes: str | None = None


class AnalysisRunResponse(BaseModel):
    """Response for an analysis run."""

    id: UUID
    status: str
    triggered_by: UUID | None = None
    total_voters_analyzed: int | None = None
    match_count: int | None = None
    mismatch_count: int | None = None
    unable_to_analyze_count: int | None = None
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAnalysisRunResponse(BaseModel):
    """Paginated list of analysis runs."""

    items: list[AnalysisRunResponse]
    pagination: PaginationMeta


class MismatchDetail(BaseModel):
    """Detail of a single boundary type mismatch."""

    boundary_type: str
    registered: str
    determined: str


class AnalysisResultResponse(BaseModel):
    """Response for a single analysis result."""

    id: UUID
    analysis_run_id: UUID
    voter_id: UUID
    voter_summary: VoterSummaryResponse | None = None
    determined_boundaries: dict[str, str]
    registered_boundaries: dict[str, str]
    match_status: str
    mismatch_details: list[MismatchDetail] | None = None
    analyzed_at: datetime

    model_config = {"from_attributes": True}


class PaginatedAnalysisResultResponse(BaseModel):
    """Paginated list of analysis results."""

    items: list[AnalysisResultResponse]
    pagination: PaginationMeta


class ComparisonItem(BaseModel):
    """A single voter's comparison between two runs."""

    voter_id: UUID
    voter_registration_number: str
    status_in_run_a: str
    status_in_run_b: str
    changed: bool


class ComparisonSummary(BaseModel):
    """Summary statistics for a run comparison."""

    newly_matched: int = 0
    newly_mismatched: int = 0
    unchanged: int = 0
    total_compared: int = 0


class AnalysisComparisonResponse(BaseModel):
    """Response comparing results across two analysis runs."""

    run_a: AnalysisRunResponse
    run_b: AnalysisRunResponse
    summary: ComparisonSummary
    items: list[ComparisonItem] = Field(default_factory=list)
