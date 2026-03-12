"""Results file loading and ballot item iteration.

Loads SoS election results JSON files and provides per-contest
iteration with parsed candidates and ingestion results.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from voter_api.lib.election_tracker.ingester import (
    IngestionResult,
    detect_election_type,
    ingest_election_results,
)
from voter_api.lib.election_tracker.parser import SoSFeed, parse_sos_feed
from voter_api.lib.results_importer.candidate_parser import (
    ParsedCandidate,
    normalize_party,
)

# Matches trailing parenthetical markers like (Rep), (Dem), (I)
_PAREN_MARKER_RE = re.compile(r"\s*\((?:Rep|Dem|I|Ind|Lib|NP)\)", re.IGNORECASE)


@dataclass(frozen=True)
class BallotItemContext:
    """Per-contest context from a results file.

    Attributes:
        ballot_item_id: SoS ballot item ID (e.g., "SHD23").
        ballot_item_name: Full contest name
            (e.g., "State House of Representatives - District 23").
        election_event_name: Feed-level election name
            (e.g., "January 6, 2026 - HD 23 Special Election Runoff").
        election_date: Election date.
        election_type: Detected election type
            (primary, general, runoff, special).
        ingestion: Extracted statewide + county results for this ballot item.
        candidates: Parsed candidate list from this ballot item.
    """

    ballot_item_id: str
    ballot_item_name: str
    election_event_name: str
    election_date: date
    election_type: str
    ingestion: IngestionResult
    candidates: list[ParsedCandidate] = field(default_factory=list)


def load_results_file(path: Path) -> SoSFeed:
    """Load and parse a SoS election results JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Validated SoSFeed model.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
        pydantic.ValidationError: If the JSON doesn't match the SoSFeed schema.
    """
    with path.open() as f:
        raw = json.load(f)
    return parse_sos_feed(raw)


def iter_ballot_items(feed: SoSFeed) -> list[BallotItemContext]:
    """Extract per-contest contexts from a parsed SoS feed.

    For each ballot item in the feed, produces a BallotItemContext with:
    - Parsed candidate information from ballot options
    - Ingestion result (statewide + county data) via the existing ingester

    Args:
        feed: Parsed SoS feed.

    Returns:
        List of BallotItemContext, one per ballot item.
    """
    election_date = date.fromisoformat(feed.electionDate)
    election_type = detect_election_type(feed.electionName)
    contexts: list[BallotItemContext] = []

    for ballot_item in feed.results.ballotItems:
        # Parse candidates from ballot options (inline to access BallotOption fields)
        candidates: list[ParsedCandidate] = []
        for option in ballot_item.ballotOptions:
            # Detect incumbent
            is_incumbent = "(I)" in option.name or "(i)" in option.name

            # Clean name: strip all parenthetical markers
            clean_name = _PAREN_MARKER_RE.sub("", option.name).strip()

            party = normalize_party(option.politicalParty)

            candidates.append(
                ParsedCandidate(
                    full_name=clean_name,
                    party=party,
                    is_incumbent=is_incumbent,
                    ballot_order=option.ballotOrder,
                    sos_ballot_option_id=option.id,
                    vote_count=option.voteCount,
                )
            )

        # Extract ingestion result for this specific ballot item
        ingestion = ingest_election_results(feed, ballot_item_id=ballot_item.id)

        contexts.append(
            BallotItemContext(
                ballot_item_id=ballot_item.id,
                ballot_item_name=ballot_item.name,
                election_event_name=feed.electionName,
                election_date=election_date,
                election_type=election_type,
                ingestion=ingestion,
                candidates=candidates,
            )
        )

    return contexts
