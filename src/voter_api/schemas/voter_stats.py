"""Pydantic v2 schemas for voter registration statistics."""

from pydantic import BaseModel


class VoterStatusCount(BaseModel):
    """Count of voters with a specific registration status."""

    status: str
    count: int


class VoterRegistrationStatsResponse(BaseModel):
    """Aggregate voter registration statistics for a boundary/district."""

    total: int
    by_status: list[VoterStatusCount]
