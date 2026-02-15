"""Pydantic v2 schemas for election tracking endpoints.

Request/response models per contracts/openapi.yaml.
"""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from voter_api.schemas.common import PaginationMeta

# --- Request schemas ---


class ElectionCreateRequest(BaseModel):
    """Request body for creating a new election."""

    name: str = Field(min_length=1, max_length=500)
    election_date: date
    election_type: Literal["special", "general", "primary", "runoff"]
    district: str = Field(min_length=1, max_length=200)
    data_source_url: HttpUrl
    refresh_interval_seconds: int = Field(default=120, ge=60)


class ElectionUpdateRequest(BaseModel):
    """Request body for updating election metadata (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=500)
    data_source_url: HttpUrl | None = None
    status: Literal["active", "finalized"] | None = None
    refresh_interval_seconds: int | None = Field(default=None, ge=60)


# --- Response schemas ---


class ElectionSummary(BaseModel):
    """Election summary for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    election_date: date
    election_type: str
    district: str
    status: str
    last_refreshed_at: datetime | None
    precincts_reporting: int | None = None
    precincts_participating: int | None = None


class ElectionDetailResponse(ElectionSummary):
    """Full election detail response."""

    data_source_url: str
    refresh_interval_seconds: int
    created_at: datetime
    updated_at: datetime


class PaginatedElectionListResponse(BaseModel):
    """Paginated list of elections."""

    items: list[ElectionSummary]
    pagination: PaginationMeta


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
    status: str
    last_refreshed_at: datetime | None
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
    status: str
    last_refreshed_at: datetime | None
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
    status: str
    last_refreshed_at: datetime | None
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
    status: str
    last_refreshed_at: datetime | None
    features: list[PrecinctElectionResultFeature] = Field(default_factory=list)
