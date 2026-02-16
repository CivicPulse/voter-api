"""Election result ingestion — extract statewide and county results from SoS feed.

Parses a SoSFeed into intermediate dataclasses suitable for persistence.
The actual database operations live in the service layer.
"""

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from voter_api.lib.election_tracker.parser import BallotItem, SoSFeed


def detect_election_type(election_name: str) -> str:
    """Infer election type from SoS feed electionName.

    Priority order (first match wins):
      1. "runoff" → "runoff"
      2. "primary" → "primary"
      3. "general" → "general"
      4. fallback → "special"

    Args:
        election_name: The electionName field from a SoS feed.

    Returns:
        One of "runoff", "primary", "general", or "special".
    """
    name_lower = election_name.lower()
    if "runoff" in name_lower:
        return "runoff"
    if "primary" in name_lower:
        return "primary"
    if "general" in name_lower:
        return "general"
    return "special"


@dataclass
class StatewideResultData:
    """Extracted statewide election result data."""

    precincts_participating: int | None
    precincts_reporting: int | None
    results_data: list[dict]
    source_created_at: datetime | None


@dataclass
class CountyResultData:
    """Extracted county-level election result data."""

    county_name: str
    county_name_normalized: str
    precincts_participating: int | None
    precincts_reporting: int | None
    results_data: list[dict]


@dataclass
class IngestionResult:
    """Complete extraction result from a SoS feed."""

    statewide: StatewideResultData
    counties: list[CountyResultData] = field(default_factory=list)


def _normalize_county_name(sos_name: str) -> str:
    """Strip ' County' suffix for boundary matching.

    Args:
        sos_name: County name from SoS feed (e.g., 'Houston County').

    Returns:
        Normalized name (e.g., 'Houston').
    """
    return sos_name.strip().removesuffix(" County").strip()


def _find_ballot_item(
    items: list[BallotItem],
    ballot_item_id: str | None,
    context: str,
    *,
    raise_on_missing: bool = True,
) -> BallotItem | None:
    """Find a ballot item by ID, or default to first item if ID is None.

    Args:
        items: List of ballot items to search.
        ballot_item_id: The ballot item ID to find, or None for first item.
        context: Context string for log/error messages (e.g., "statewide results").
        raise_on_missing: If True, raise ValueError when ballot_item_id not found.
            If False, return None.

    Returns:
        The matching ballot item, or None if items is empty (and raise_on_missing
        is False or ballot_item_id is None), or not found (when raise_on_missing=False).

    Raises:
        ValueError: If ballot_item_id is specified but not found (or items is empty)
            and raise_on_missing=True.
    """
    if not items:
        if ballot_item_id is not None and raise_on_missing:
            msg = f"No ballot items found in {context} to search for '{ballot_item_id}'."
            raise ValueError(msg)
        return None

    if ballot_item_id is None:
        return items[0]

    for item in items:
        if item.id == ballot_item_id:
            return item

    available_ids = [item.id for item in items]
    if raise_on_missing:
        msg = f"Ballot item '{ballot_item_id}' not found in {context}. Available: {available_ids}"
        raise ValueError(msg)

    logger.info(
        "Ballot item '{}' not found in {} (available: {})",
        ballot_item_id,
        context,
        available_ids,
    )
    return None


def ingest_election_results(
    feed: SoSFeed,
    ballot_item_id: str | None = None,
) -> IngestionResult:
    """Extract statewide and county-level results from a parsed SoS feed.

    Args:
        feed: Parsed SoS feed data.
        ballot_item_id: SoS ballot item ID to extract. When None, defaults
            to the first ballotItem (backward compatible).

    Returns:
        IngestionResult containing statewide and county data ready for persistence.

    Raises:
        ValueError: If ballot_item_id is specified but not found in statewide results.
    """
    # --- Statewide result extraction ---
    statewide_ballot = _find_ballot_item(
        feed.results.ballotItems,
        ballot_item_id,
        "statewide results",
        raise_on_missing=True,
    )

    precincts_participating = statewide_ballot.precinctsParticipating if statewide_ballot else None
    precincts_reporting = statewide_ballot.precinctsReporting if statewide_ballot else None
    results_data = [opt.model_dump() for opt in statewide_ballot.ballotOptions] if statewide_ballot else []

    source_created_at = None
    try:
        source_created_at = feed.created_at_dt
    except (ValueError, TypeError):
        logger.warning("Could not parse createdAt from SoS feed: {}", feed.createdAt)

    statewide = StatewideResultData(
        precincts_participating=precincts_participating,
        precincts_reporting=precincts_reporting,
        results_data=results_data,
        source_created_at=source_created_at,
    )

    # --- County results extraction ---
    counties: list[CountyResultData] = []

    for local_result in feed.localResults:
        county_name = local_result.name
        county_name_normalized = _normalize_county_name(county_name)

        if not county_name_normalized:
            logger.warning("Skipping county with empty normalized name: {}", county_name)
            continue

        county_ballot = _find_ballot_item(
            local_result.ballotItems,
            ballot_item_id,
            f"county '{county_name}'",
            raise_on_missing=False,
        )
        if county_ballot is None:
            continue

        county_precincts_participating = county_ballot.precinctsParticipating
        county_precincts_reporting = county_ballot.precinctsReporting
        county_results_data = [opt.model_dump() for opt in county_ballot.ballotOptions]

        counties.append(
            CountyResultData(
                county_name=county_name,
                county_name_normalized=county_name_normalized,
                precincts_participating=county_precincts_participating,
                precincts_reporting=county_precincts_reporting,
                results_data=county_results_data,
            )
        )

    logger.info("Extracted results from SoS feed: {} counties", len(counties))

    return IngestionResult(statewide=statewide, counties=counties)
