"""CandidacyJSONL Pydantic model.

Defines the data contract for candidacy (candidate-election junction)
records in JSONL format. A candidacy links a candidate (person entity)
to a specific election contest with contest-specific fields like party,
filing_status, and ballot_order.

Maps to the target Candidacy DB table (new junction table in Phase 2).
"""

import uuid
from datetime import date

from pydantic import BaseModel, Field

from voter_api.schemas.jsonl.enums import FilingStatus


class CandidacyJSONL(BaseModel):
    """JSONL record for a candidacy (candidate-election junction).

    Links a candidate (person entity) to a specific election contest.
    Contest-specific fields live here; person-level fields live in
    CandidateJSONL.
    """

    schema_version: int = Field(
        default=1,
        description="Schema version integer. Increment on breaking changes.",
    )
    id: uuid.UUID = Field(
        description="UUID of this candidacy record. From markdown metadata.",
    )
    candidate_id: uuid.UUID = Field(
        description="UUID of the candidate (person). From candidate file metadata.",
    )
    election_id: uuid.UUID = Field(
        description="UUID of the election contest. From contest file metadata.",
    )

    # Contest-specific fields
    party: str | None = Field(
        default=None,
        description="Party affiliation for this contest. Null for non-partisan races.",
    )
    filing_status: FilingStatus = Field(
        default=FilingStatus.QUALIFIED,
        description="Candidate filing status. One of: qualified, withdrawn, disqualified, write_in.",
    )
    is_incumbent: bool = Field(
        default=False,
        description="Whether the candidate is the incumbent for this seat.",
    )
    occupation: str | None = Field(
        default=None,
        description="Occupation as listed in SOS data. Title case.",
    )
    qualified_date: date | None = Field(
        default=None,
        description="Date candidate qualified for the ballot (YYYY-MM-DD).",
    )
    ballot_order: int | None = Field(
        default=None,
        description="Position on ballot. Typically set from SOS results data.",
    )
    sos_ballot_option_id: str | None = Field(
        default=None,
        description="SOS ballot option ID from results feed for matching.",
    )
    contest_name: str | None = Field(
        default=None,
        description="Exact SOS contest name for matching. From Name (SOS) metadata.",
    )
