"""Analyzer library — public API for location analysis.

Provides spatial queries and boundary comparison for voter
registration-location mismatch detection.
"""

from voter_api.lib.analyzer.comparator import (
    BOUNDARY_TYPE_TO_VOTER_FIELD,
    ComparisonResult,
    compare_boundaries,
    extract_registered_boundaries,
)
from voter_api.lib.analyzer.spatial import find_voter_boundaries, find_voter_boundaries_batch

__all__ = [
    "BOUNDARY_TYPE_TO_VOTER_FIELD",
    "ComparisonResult",
    "compare_boundaries",
    "extract_registered_boundaries",
    "find_voter_boundaries",
    "find_voter_boundaries_batch",
]
