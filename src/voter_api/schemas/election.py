"""Pydantic v2 schemas for election tracking endpoints.

Request/response models per contracts/openapi.yaml.
"""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, computed_field, model_validator

from voter_api.lib.election_tracker import ElectionType
from voter_api.schemas.common import PaginationMeta

# ElectionStatus defined here — schema/service layer concept only
ElectionStatus = Literal["active", "finalized"]

# --- Request schemas ---


class ElectionCreateRequest(BaseModel):
    """Request body for creating a new election."""

    name: str = Field(min_length=1, max_length=500)
    election_date: date
    election_type: ElectionType
    district: str = Field(min_length=1, max_length=200)
    source: Literal["sos_feed", "manual"]
    data_source_url: HttpUrl | None = None
    boundary_id: uuid.UUID | None = None
    refresh_interval_seconds: int = Field(default=120, ge=60)
    ballot_item_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="SoS ballot item ID for multi-race feeds. Defaults to first race if null.",
    )
    status: ElectionStatus = "active"

    @model_validator(mode="after")
    def validate_source_fields(self) -> "ElectionCreateRequest":
        """Enforce source-specific field requirements."""
        if self.source == "sos_feed" and self.data_source_url is None:
            raise ValueError("data_source_url is required for sos_feed elections")
        if self.source == "manual":
            if self.data_source_url is not None:
                raise ValueError("data_source_url must not be set for manual elections")
            if self.boundary_id is None:
                raise ValueError("boundary_id is required for manual elections")
        return self


class ElectionUpdateRequest(BaseModel):
    """Request body for updating election metadata (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    data_source_url: HttpUrl | None = None
    status: ElectionStatus | None = None
    refresh_interval_seconds: int | None = Field(default=None, ge=60)
    ballot_item_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="SoS ballot item ID for multi-race feeds.",
    )
    # Election metadata enrichment fields (010-election-info)
    description: str | None = None
    purpose: str | None = None
    eligibility_description: str | None = None
    registration_deadline: date | None = None
    early_voting_start: date | None = None
    early_voting_end: date | None = None
    absentee_request_deadline: date | None = None
    qualifying_start: datetime | None = None
    qualifying_end: datetime | None = None


class ElectionLinkRequest(BaseModel):
    """Request body for linking a manual election to a SOS feed URL."""

    data_source_url: HttpUrl
    ballot_item_id: str | None = Field(default=None, min_length=1, max_length=50)


# --- Response schemas ---


class ElectionSummary(BaseModel):
    """Election summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    election_date: date
    election_type: ElectionType
    district: str
    status: ElectionStatus
    source: str
    election_stage: str | None = None
    last_refreshed_at: datetime | None = None
    precincts_reporting: int | None = None
    precincts_participating: int | None = None
    ballot_item_id: str | None = None
    boundary_id: uuid.UUID | None = None
    election_event_id: uuid.UUID | None = None
    district_type: str | None = None
    district_identifier: str | None = None
    district_party: str | None = None
    # Election metadata enrichment fields (010-election-info)
    description: str | None = None
    purpose: str | None = None
    eligibility_description: str | None = None
    registration_deadline: date | None = None
    early_voting_start: date | None = None
    early_voting_end: date | None = None
    absentee_request_deadline: date | None = None
    qualifying_start: datetime | None = None
    qualifying_end: datetime | None = None


class ElectionDetailResponse(ElectionSummary):
    """Full election detail response."""

    data_source_url: str | None = None
    refresh_interval_seconds: int
    created_at: datetime
    updated_at: datetime


class PaginatedElectionListResponse(BaseModel):
    """Paginated list of elections."""

    items: list[ElectionSummary]
    pagination: PaginationMeta


class CapabilitiesResponse(BaseModel):
    """Capabilities discovery response for the elections API."""

    supported_filters: list[str] = Field(description="Filter parameter names accepted by GET /elections")
    endpoints: dict[str, bool] = Field(description="Available sub-endpoints and their status")


class FilterOptionsResponse(BaseModel):
    """Valid filter values for election search dropdowns."""

    race_categories: list[str] = Field(default_factory=list)
    counties: list[str] = Field(default_factory=list)
    election_dates: list[date] = Field(default_factory=list)
    total_elections: int = 0


class VoteMethodResult(BaseModel):
    """Vote method breakdown."""

    group_name: str
    vote_count: int = 0


class CandidateResult(BaseModel):
    """Candidate result with vote counts and method breakdown."""

    id: str
    name: str
    political_party: str
    ballot_order: int
    vote_count: int = 0
    group_results: list[VoteMethodResult] = Field(default_factory=list)


class CountyResultSummary(BaseModel):
    """County-level result summary."""

    county_name: str
    precincts_participating: int | None = None
    precincts_reporting: int | None = None
    candidates: list[CandidateResult] = Field(default_factory=list)


class ElectionResultsResponse(BaseModel):
    """Full election results response with statewide and county data."""

    election_id: uuid.UUID
    election_name: str
    election_date: date
    status: ElectionStatus
    last_refreshed_at: datetime | None = None
    precincts_participating: int | None = None
    precincts_reporting: int | None = None
    candidates: list[CandidateResult] = Field(default_factory=list)
    county_results: list[CountyResultSummary] = Field(default_factory=list)


class RawCountyResult(BaseModel):
    """County-level raw result with original SOS field names preserved."""

    county_name: str
    precincts_participating: int | None = None
    precincts_reporting: int | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)


class RawElectionResultsResponse(BaseModel):
    """Election results with raw SOS ballot option data (camelCase preserved)."""

    election_id: uuid.UUID
    election_name: str
    election_date: date
    status: ElectionStatus
    last_refreshed_at: datetime | None = None
    source_created_at: datetime | None = None
    precincts_participating: int | None = None
    precincts_reporting: int | None = None
    statewide_results: list[dict[str, Any]] = Field(default_factory=list)
    county_results: list[RawCountyResult] = Field(default_factory=list)


class ElectionResultFeature(BaseModel):
    """GeoJSON Feature for a county's election results."""

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any]


class ElectionResultFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection of county election results."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    election_id: uuid.UUID
    election_name: str
    election_date: date
    status: ElectionStatus
    last_refreshed_at: datetime | None = None
    features: list[ElectionResultFeature] = Field(default_factory=list)


class RefreshResponse(BaseModel):
    """Response from a manual refresh operation."""

    election_id: uuid.UUID
    refreshed_at: datetime
    precincts_reporting: int | None = None
    precincts_participating: int | None = None
    counties_updated: int = 0


# --- Precinct-level GeoJSON schemas ---


class PrecinctCandidateResult(BaseModel):
    """Per-candidate result within a single precinct."""

    id: str
    name: str
    political_party: str
    ballot_order: int
    vote_count: int = 0
    reporting_status: str | None = None
    group_results: list[VoteMethodResult] = Field(default_factory=list)


class PrecinctElectionResultFeature(BaseModel):
    """GeoJSON Feature for a precinct's election results."""

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any]


class PrecinctElectionResultFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection of precinct-level election results."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    election_id: uuid.UUID
    election_name: str
    election_date: date
    status: ElectionStatus
    last_refreshed_at: datetime | None = None
    features: list[PrecinctElectionResultFeature] = Field(default_factory=list)


# --- Feed import schemas ---


class FeedImportRequest(BaseModel):
    """Request body for importing races from an SoS feed."""

    data_source_url: HttpUrl = Field(description="SoS feed URL containing one or more races")
    election_type: ElectionType | None = Field(
        default=None,
        description="Election type to assign to all created elections. Auto-detected from feed name when null.",
    )
    refresh_interval_seconds: int = Field(
        default=120,
        ge=60,
        description="Refresh interval for all imported elections",
    )
    auto_refresh: bool = Field(
        default=True,
        description="Perform initial refresh after creating elections",
    )


class FeedRaceSummary(BaseModel):
    """Summary of a single race discovered in a feed."""

    ballot_item_id: str = Field(min_length=1)
    name: str
    candidate_count: int = Field(default=0, ge=0)
    statewide_precincts_participating: int | None = None
    statewide_precincts_reporting: int | None = None


class FeedImportPreviewResponse(BaseModel):
    """Preview of races available in a feed before import."""

    data_source_url: str
    election_date: date
    election_name: str
    detected_election_type: ElectionType
    races: list[FeedRaceSummary]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_races(self) -> int:
        """Number of races discovered in the feed."""
        return len(self.races)


class FeedImportedElection(BaseModel):
    """Information about an election created during feed import."""

    election_id: uuid.UUID
    ballot_item_id: str
    name: str
    election_date: date
    status: ElectionStatus
    refreshed: bool
    precincts_reporting: int | None = None
    precincts_participating: int | None = None


class FeedImportResponse(BaseModel):
    """Response from a feed import operation."""

    elections_skipped: int = 0
    elections: list[FeedImportedElection]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def elections_created(self) -> int:
        """Number of elections successfully created."""
        return len(self.elections)
