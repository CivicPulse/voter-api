"""Election tracker library — fetch, parse, and ingest SoS election results.

Public API:
    - parse_sos_feed: Parse raw JSON into validated SoSFeed model
    - fetch_election_results: Async HTTP fetch + parse from SoS feed URL
    - ingest_election_results: Extract statewide + county results from a parsed SoS feed
    - SoSFeed: Top-level feed model
    - FetchError: HTTP/parse error type
"""

from voter_api.lib.election_tracker.fetcher import FetchError, fetch_election_results, validate_url_domain
from voter_api.lib.election_tracker.ingester import (
    CountyResultData,
    ElectionType,
    IngestionResult,
    StatewideResultData,
    detect_election_type,
    ingest_election_results,
)
from voter_api.lib.election_tracker.parser import SoSFeed, parse_sos_feed

__all__ = [
    "CountyResultData",
    "ElectionType",
    "FetchError",
    "IngestionResult",
    "SoSFeed",
    "StatewideResultData",
    "detect_election_type",
    "fetch_election_results",
    "ingest_election_results",
    "parse_sos_feed",
    "validate_url_domain",
]
