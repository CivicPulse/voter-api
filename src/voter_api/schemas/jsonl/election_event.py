"""ElectionEventJSONL Pydantic model.

Defines the data contract for election event records in JSONL format.
An election event represents a single election day that groups multiple
contests (elections). Calendar dates and feed configuration live here,
not on individual election contests.

Maps to the target ElectionEvent DB table (post-Phase 2 migration).
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from voter_api.schemas.jsonl.enums import ElectionType


class ElectionEventJSONL(BaseModel):
    """JSONL record for an election event (election day).

    Groups multiple election contests under a single event date.
    Calendar fields (registration deadline, early voting, etc.) and
    feed configuration live here rather than being duplicated across
    individual contest records.
    """

    schema_version: int = Field(
        default=1,
        description="Schema version integer. Increment on breaking changes.",
    )
    id: uuid.UUID = Field(
        description="UUID from markdown overview metadata table. Required.",
    )
    event_date: date = Field(
        description="Election day date (YYYY-MM-DD).",
    )
    event_name: str = Field(
        description="Display name of the election event, e.g. 'May 19, 2026 - General Primary Election'.",
    )
    event_type: ElectionType = Field(
        description="Base election type. One of: general_primary, general, special, special_primary, municipal.",
    )

    # Calendar fields (optional -- populated from markdown overview)
    registration_deadline: date | None = Field(
        default=None,
        description="Voter registration deadline date (YYYY-MM-DD).",
    )
    early_voting_start: date | None = Field(
        default=None,
        description="First day of early voting (YYYY-MM-DD).",
    )
    early_voting_end: date | None = Field(
        default=None,
        description="Last day of early voting (YYYY-MM-DD).",
    )
    absentee_request_deadline: date | None = Field(
        default=None,
        description="Deadline to request an absentee ballot (YYYY-MM-DD).",
    )
    qualifying_start: date | None = Field(
        default=None,
        description="First day of candidate qualifying period (YYYY-MM-DD).",
    )
    qualifying_end: date | None = Field(
        default=None,
        description="Last day of candidate qualifying period (YYYY-MM-DD).",
    )

    # Feed fields (optional -- populated when results feed URL is known)
    data_source_url: str | None = Field(
        default=None,
        description="SOS results feed URL for this election event. Set when available.",
    )
    last_refreshed_at: datetime | None = Field(
        default=None,
        description="Timestamp of last results feed refresh (ISO 8601 with timezone).",
    )
    refresh_interval_seconds: int | None = Field(
        default=None,
        description="Seconds between results feed refresh cycles. Minimum 60.",
    )
