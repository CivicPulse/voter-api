"""CandidateJSONL and CandidateLinkJSONL Pydantic models.

Defines the data contract for candidate (person entity) records in JSONL
format. A candidate represents a person who runs for office. Contest-specific
fields (party, filing_status, ballot_order, etc.) live on CandidacyJSONL,
not here.

Maps to the target Candidate DB table (post-Phase 2 migration) where
candidates are person entities decoupled from specific elections.
"""

import uuid

from pydantic import BaseModel, Field

from voter_api.schemas.jsonl.enums import LinkType


class CandidateLinkJSONL(BaseModel):
    """Embedded model for a candidate's external link.

    Typed URL entry matching the DB constraint vocabulary for link types.
    """

    link_type: LinkType = Field(
        description="Link type. One of: website, campaign, facebook, twitter, instagram, youtube, linkedin, other.",
    )
    url: str = Field(
        description="Full URL of the external link.",
    )
    label: str | None = Field(
        default=None,
        description="Optional display label for the link.",
    )


class CandidateJSONL(BaseModel):
    """JSONL record for a candidate (person entity).

    Represents a person who runs for office, decoupled from any specific
    election. Person-level data (bio, photo, email, links) lives here.
    Contest-specific data (party, filing_status, ballot_order) lives on
    CandidacyJSONL.

    CRITICAL: This model does NOT have an election_id field. The
    candidate-to-election relationship is represented by CandidacyJSONL.
    """

    schema_version: int = Field(
        default=1,
        description="Schema version integer. Increment on breaking changes.",
    )
    id: uuid.UUID = Field(
        description="UUID from candidate file metadata table. Required.",
    )
    full_name: str = Field(
        description="Full name of the candidate as it appears on the ballot.",
    )

    # Person-level fields (optional)
    bio: str | None = Field(
        default=None,
        description="Biographical text for the candidate.",
    )
    photo_url: str | None = Field(
        default=None,
        description="URL to the candidate's photo.",
    )
    email: str | None = Field(
        default=None,
        description="Contact email address for the candidate.",
    )
    home_county: str | None = Field(
        default=None,
        description="County of residence.",
    )
    municipality: str | None = Field(
        default=None,
        description="Municipality of residence.",
    )

    # Links (optional list of typed URLs)
    links: list[CandidateLinkJSONL] = Field(
        default_factory=list,
        description="List of external links (website, social media, etc.).",
    )

    # External IDs for cross-referencing with other data providers
    external_ids: dict[str, str] | None = Field(
        default=None,
        description="External IDs for cross-referencing (e.g. ballotpedia, open_states, vpap).",
    )
