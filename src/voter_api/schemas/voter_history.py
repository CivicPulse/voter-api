"""Voter history Pydantic v2 request/response schemas."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from voter_api.schemas.common import PaginationMeta


class VoterHistoryRecord(BaseModel):
    """A single voter participation record."""

    id: UUID
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


class BallotStyleBreakdown(BaseModel):
    """Participation count for a single ballot style."""

    ballot_style: str
    count: int


class ParticipationStatsResponse(BaseModel):
    """Aggregate participation statistics for an election."""

    election_id: UUID
    total_participants: int
    by_county: list[CountyBreakdown] = Field(default_factory=list)
    by_ballot_style: list[BallotStyleBreakdown] = Field(default_factory=list)


class ParticipationSummary(BaseModel):
    """Lightweight participation summary for voter detail enrichment."""

    total_elections: int = 0
    last_election_date: date | None = None
