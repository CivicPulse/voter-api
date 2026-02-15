"""SoS feed JSON parser and Pydantic validation models.

Parses the Georgia Secretary of State election results JSON feed
into validated Pydantic models.

Field names use camelCase to match the SoS feed JSON structure.
"""

# ruff: noqa: N815

from datetime import datetime

from pydantic import BaseModel, Field


class GroupResult(BaseModel):
    """Vote method breakdown (e.g., Election Day, Advance Voting)."""

    groupName: str
    voteCount: int = 0
    isFromVirtualPrecinct: bool = False


class BallotOption(BaseModel):
    """A candidate or ballot option with vote counts."""

    id: str
    name: str
    ballotOrder: int = 1
    voteCount: int = 0
    politicalParty: str = ""
    groupResults: list[GroupResult] = Field(default_factory=list)
    precinctResults: list[dict] | None = None


class BallotItem(BaseModel):
    """A contest or race on the ballot."""

    id: str
    name: str
    voteFor: int = 1
    precinctsParticipating: int | None = None
    precinctsReporting: int | None = None
    ballotOptions: list[BallotOption] = Field(default_factory=list)


class LocalResult(BaseModel):
    """County-level results from the SoS feed."""

    id: str
    name: str
    ballotItems: list[BallotItem] = Field(default_factory=list)


class SoSResults(BaseModel):
    """Statewide results container."""

    id: str
    name: str
    ballotItems: list[BallotItem] = Field(default_factory=list)


class SoSFeed(BaseModel):
    """Top-level SoS election results feed."""

    electionDate: str
    electionName: str
    createdAt: str
    results: SoSResults
    localResults: list[LocalResult] = Field(default_factory=list)

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
