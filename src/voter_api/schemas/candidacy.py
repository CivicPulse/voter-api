"""Pydantic v2 schemas for candidacy (candidate-election junction) endpoints.

Response models for the candidacy relationship between candidates and elections.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class CandidacySummaryResponse(BaseModel):
    """Candidacy summary for embedding in CandidateResponse.

    Provides the essential fields about a candidate's participation
    in a specific election contest.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    election_id: uuid.UUID
    party: str | None = None
    filing_status: str
    contest_name: str | None = None


class CandidacyResponse(BaseModel):
    """Full candidacy detail response.

    Contains all contest-specific fields for a candidate's participation
    in a specific election.
    """

    model_config = {"from_attributes": True}

    id: uuid.UUID
    candidate_id: uuid.UUID
    election_id: uuid.UUID
    party: str | None = None
    filing_status: str
    ballot_order: int | None = None
    is_incumbent: bool
    contest_name: str | None = None
    qualified_date: date | None = None
    occupation: str | None = None
    home_county: str | None = None
    municipality: str | None = None
    created_at: datetime
    updated_at: datetime
