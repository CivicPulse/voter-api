"""Voter history Pydantic v2 request/response schemas."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


@dataclass(frozen=True)
class ParticipationFilters:
    """Bundle of filter parameters for the election participation endpoint.

    Groups voter-history filters and voter-table filters into a single
    object to reduce parameter counts in route handlers and service functions.
    """

    county: str | None = None
    ballot_style: str | None = None
    absentee: bool | None = None
    provisional: bool | None = None
    supplemental: bool | None = None
    q: str | None = None
    county_precinct: str | None = None
    congressional_district: str | None = None
    state_senate_district: str | None = None
    state_house_district: str | None = None
    county_commission_district: str | None = None
    school_board_district: str | None = None
    voter_status: str | None = None
    has_district_mismatch: bool | None = None


class VoterHistoryRecord(BaseModel):
    """A single voter participation record."""

    id: UUID
    election_id: UUID | None = None
    voter_registration_number: str
    county: str
    election_date: date
    election_type: str
    normalized_election_type: str
    party: str | None = None
    ballot_style: str | None = None
    absentee: bool
    provisional: bool
    supplemental: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedVoterHistoryResponse(BaseModel):
    """Paginated list of voter history records."""

    items: list[VoterHistoryRecord]
    pagination: PaginationMeta


class ElectionParticipationRecord(BaseModel):
    """A voter participation record in the context of an election query."""

    id: UUID
    voter_id: UUID | None = None
    first_name: str | None = None
    last_name: str | None = None
    has_district_mismatch: bool | None = None
    voter_registration_number: str
    county: str
    election_date: date
    election_type: str
    normalized_election_type: str
    party: str | None = None
    ballot_style: str | None = None
    absentee: bool
    provisional: bool
    supplemental: bool

    model_config = {"from_attributes": True}


class PaginatedElectionParticipationResponse(BaseModel):
    """Paginated list of election participation records."""

    items: list[ElectionParticipationRecord]
    pagination: PaginationMeta


class CountyBreakdown(BaseModel):
    """Participation count for a single county."""

    county: str
    count: int

    model_config = {"from_attributes": True}


class BallotStyleBreakdown(BaseModel):
    """Participation count for a single ballot style."""

    ballot_style: str
    count: int

    model_config = {"from_attributes": True}


class PrecinctBreakdown(BaseModel):
    """Participation count for a single precinct."""

    precinct: str
    precinct_name: str | None = None
    count: int

    model_config = {"from_attributes": True}


class ParticipationStatsResponse(BaseModel):
    """Aggregate participation statistics for an election."""

    election_id: UUID
    total_participants: int
    total_eligible_voters: int | None = None
    turnout_percentage: float | None = None
    by_county: list[CountyBreakdown] = Field(default_factory=list)
    by_ballot_style: list[BallotStyleBreakdown] = Field(default_factory=list)
    by_precinct: list[PrecinctBreakdown] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ParticipationSummary(BaseModel):
    """Lightweight participation summary for voter detail enrichment."""

    total_elections: int = 0
    last_election_date: date | None = None

    model_config = {"from_attributes": True}
