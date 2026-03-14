"""ElectionJSONL Pydantic model.

Defines the data contract for election contest records in JSONL format.
An election represents a single contest (e.g. "Governor - Republican Primary")
within an election event. Calendar fields live on ElectionEventJSONL, not here.

Maps to the target Election DB table (post-Phase 2 migration).
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from voter_api.schemas.jsonl.enums import ElectionStage, ElectionType


class ElectionJSONL(BaseModel):
    """JSONL record for a single election contest.

    Maps 1:1 to the elections DB table. Import-relevant fields are
    populated from markdown; feed-related fields are optional.

    CRITICAL: Calendar fields (registration_deadline, early_voting_start,
    etc.) are NOT on this model. They live on ElectionEventJSONL.
    """

    schema_version: int = Field(
        default=1,
        description="Schema version integer. Increment on breaking changes.",
    )
    id: uuid.UUID = Field(
        description="UUID from markdown contest metadata table. Required.",
    )
    election_event_id: uuid.UUID = Field(
        description="UUID of the parent ElectionEvent (overview file).",
    )
    name: str = Field(
        description="Display name matching the H1 heading in the contest markdown file.",
    )
    name_sos: str | None = Field(
        default=None,
        description="Exact SOS contest name from the Name (SOS) metadata field.",
    )
    election_date: date = Field(
        description="Election day date (YYYY-MM-DD).",
    )
    election_type: ElectionType = Field(
        description="Base election type. One of: general_primary, general, special, special_primary, municipal.",
    )
    election_stage: ElectionStage = Field(
        default=ElectionStage.ELECTION,
        description="Resolution mechanism. One of: election, runoff, recount.",
    )

    # District resolution fields
    district: str | None = Field(
        default=None,
        description="Free-text district name from legacy data. Being replaced by boundary_type + district_identifier.",
    )
    boundary_type: str | None = Field(
        default=None,
        description="Exact DB boundary type value resolved from Body/Seat reference.",
    )
    district_identifier: str | None = Field(
        default=None,
        description="Boundary identifier resolved from Body/Seat reference.",
    )
    boundary_id: uuid.UUID | None = Field(
        default=None,
        description="UUID of the resolved boundary polygon. Set during import when boundary exists.",
    )
    district_party: str | None = Field(
        default=None,
        description="Party restriction for this district contest (e.g. 'R' for Republican primary).",
    )

    # Feed and source fields (optional)
    data_source_url: str | None = Field(
        default=None,
        description="SOS results feed URL for this specific contest.",
    )
    source_name: str | None = Field(
        default=None,
        description="Human-readable name of the data source.",
    )
    source: str | None = Field(
        default=None,
        description="Source type. One of: sos_feed, manual, linked.",
    )
    ballot_item_id: str | None = Field(
        default=None,
        description="SOS ballot item ID from results feed.",
    )
    status: str | None = Field(
        default=None,
        description="Contest status. One of: active, finalized.",
    )

    # Refresh fields (optional)
    last_refreshed_at: datetime | None = Field(
        default=None,
        description="Timestamp of last results feed refresh (ISO 8601 with timezone).",
    )
    refresh_interval_seconds: int | None = Field(
        default=None,
        description="Seconds between results feed refresh cycles.",
    )

    # Geographic eligibility scoping
    eligible_county: str | None = Field(
        default=None,
        description="County restriction from candidate CSV COUNTY column.",
    )
    eligible_municipality: str | None = Field(
        default=None,
        description="Municipality restriction from candidate CSV MUNICIPALITY column.",
    )
