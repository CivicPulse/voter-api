"""Election result ingestion — extract statewide and county results from SoS feed.

Parses a SoSFeed into intermediate dataclasses suitable for persistence.
The actual database operations live in the service layer.
"""

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from voter_api.lib.election_tracker.parser import SoSFeed


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


def ingest_election_results(feed: SoSFeed) -> IngestionResult:
    """Extract statewide and county-level results from a parsed SoS feed.

    Args:
        feed: Parsed SoS feed data.

    Returns:
        IngestionResult containing statewide and county data ready for persistence.
    """
    # --- Statewide result extraction ---
    statewide_ballot = feed.results.ballotItems[0] if feed.results.ballotItems else None

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

        county_ballot = local_result.ballotItems[0] if local_result.ballotItems else None
        county_precincts_participating = county_ballot.precinctsParticipating if county_ballot else None
        county_precincts_reporting = county_ballot.precinctsReporting if county_ballot else None
        county_results_data = [opt.model_dump() for opt in county_ballot.ballotOptions] if county_ballot else []

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
