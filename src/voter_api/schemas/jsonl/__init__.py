"""JSONL schema models for the election data import pipeline.

Public API for the four JSONL data contracts that define the
machine-readable format for election data import. These Pydantic
models are the single source of truth for JSONL validation.

Import order: election_events -> elections -> candidates -> candidacies
"""

from voter_api.schemas.jsonl.candidacy import CandidacyJSONL
from voter_api.schemas.jsonl.candidate import CandidateJSONL, CandidateLinkJSONL
from voter_api.schemas.jsonl.election import ElectionJSONL
from voter_api.schemas.jsonl.election_event import ElectionEventJSONL
from voter_api.schemas.jsonl.enums import (
    BoundaryType,
    ElectionStage,
    ElectionType,
    FilingStatus,
    LinkType,
)

__all__ = [
    # Models
    "CandidacyJSONL",
    "CandidateJSONL",
    "CandidateLinkJSONL",
    "ElectionEventJSONL",
    "ElectionJSONL",
    # Enums
    "BoundaryType",
    "ElectionStage",
    "ElectionType",
    "FilingStatus",
    "LinkType",
]
