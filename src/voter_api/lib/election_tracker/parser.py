"""SoS feed JSON parser and Pydantic validation models.

Parses the Georgia Secretary of State election results JSON feed
into validated Pydantic models.

Field names use camelCase to match the SoS feed JSON structure.
"""

# ruff: noqa: N815

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _coerce_null_to_list(v: Any) -> Any:
    """Coerce explicit JSON null to empty list."""
    return v if v is not None else []


def _coerce_null_to_int(v: Any) -> Any:
    """Coerce explicit JSON null to 0."""
    return v if v is not None else 0


def _coerce_null_to_str(v: Any) -> Any:
    """Coerce explicit JSON null to empty string."""
    return v if v is not None else ""


class GroupResult(BaseModel):
    """Vote method breakdown (e.g., Election Day, Advance Voting)."""

    groupName: str
    voteCount: int = 0
    isFromVirtualPrecinct: bool = False

    @field_validator("voteCount", mode="before")
    @classmethod
    def _coerce_vote_count(cls, v: Any) -> Any:
        return _coerce_null_to_int(v)


class BallotOption(BaseModel):
    """A candidate or ballot option with vote counts."""

    id: str
    name: str
    ballotOrder: int = 1
    voteCount: int = 0
    politicalParty: str = ""
    groupResults: list[GroupResult] = Field(default_factory=list)
    precinctResults: list[dict] | None = None

    @field_validator("voteCount", mode="before")
    @classmethod
    def _coerce_vote_count(cls, v: Any) -> Any:
        return _coerce_null_to_int(v)

    @field_validator("politicalParty", mode="before")
    @classmethod
    def _coerce_party(cls, v: Any) -> Any:
        return _coerce_null_to_str(v)

    @field_validator("groupResults", mode="before")
    @classmethod
    def _coerce_group_results(cls, v: Any) -> Any:
        return _coerce_null_to_list(v)


class BallotItem(BaseModel):
    """A contest or race on the ballot."""

    id: str
    name: str
    voteFor: int = 1
    precinctsParticipating: int | None = None
    precinctsReporting: int | None = None
    ballotOptions: list[BallotOption] = Field(default_factory=list)

    @field_validator("ballotOptions", mode="before")
    @classmethod
    def _coerce_ballot_options(cls, v: Any) -> Any:
        return _coerce_null_to_list(v)


class LocalResult(BaseModel):
    """County-level results from the SoS feed."""

    id: str
    name: str
    ballotItems: list[BallotItem] = Field(default_factory=list)

    @field_validator("ballotItems", mode="before")
    @classmethod
    def _coerce_ballot_items(cls, v: Any) -> Any:
        return _coerce_null_to_list(v)


class SoSResults(BaseModel):
    """Statewide results container."""

    id: str
    name: str
    ballotItems: list[BallotItem] = Field(default_factory=list)

    @field_validator("ballotItems", mode="before")
    @classmethod
    def _coerce_ballot_items(cls, v: Any) -> Any:
        return _coerce_null_to_list(v)


class SoSFeed(BaseModel):
    """Top-level SoS election results feed."""

    electionDate: str
    electionName: str
    createdAt: str
    results: SoSResults
    localResults: list[LocalResult] = Field(default_factory=list)

    @field_validator("localResults", mode="before")
    @classmethod
    def _coerce_local_results(cls, v: Any) -> Any:
        return _coerce_null_to_list(v)

    @property
    def created_at_dt(self) -> datetime:
        """Parse createdAt string to datetime."""
        return datetime.fromisoformat(self.createdAt)


def parse_sos_feed(raw_json: dict) -> SoSFeed:
    """Parse and validate a raw SoS feed JSON dict into a SoSFeed model.

    Args:
        raw_json: The raw JSON dictionary from the SoS feed.

    Returns:
        A validated SoSFeed instance.

    Raises:
        pydantic.ValidationError: If the JSON structure is invalid.
    """
    return SoSFeed.model_validate(raw_json)
