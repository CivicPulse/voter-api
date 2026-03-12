"""Results importer library -- parse SoS election results JSON files.

Public API:
    - load_results_file: Load JSON file into SoSFeed
    - iter_ballot_items: Extract per-contest contexts with candidates
    - validate_results_file: Pre-import validation
    - BallotItemContext: Per-contest data container
    - ParsedCandidate: Parsed candidate from ballot option
    - parse_candidate_name: Name/party parsing utility
    - normalize_party: Party code normalization
"""

from voter_api.lib.results_importer.candidate_parser import (
    ParsedCandidate,
    normalize_party,
    parse_candidate_name,
)
from voter_api.lib.results_importer.parser import (
    BallotItemContext,
    iter_ballot_items,
    load_results_file,
)
from voter_api.lib.results_importer.validator import validate_results_file

__all__ = [
    "BallotItemContext",
    "ParsedCandidate",
    "iter_ballot_items",
    "load_results_file",
    "normalize_party",
    "parse_candidate_name",
    "validate_results_file",
]
