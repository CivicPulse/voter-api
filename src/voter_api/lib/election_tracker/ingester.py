"""Election result ingestion — upsert statewide and county results.

Accepts a parsed SoSFeed and persists results to the database using
upsert semantics (replace existing data on refresh).
"""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.election_tracker.parser import SoSFeed
from voter_api.models.election import ElectionCountyResult, ElectionResult


def _normalize_county_name(sos_name: str) -> str:
    """Strip ' County' suffix for boundary matching.

    Args:
        sos_name: County name from SoS feed (e.g., 'Houston County').

    Returns:
        Normalized name (e.g., 'Houston').
    """
    return sos_name.strip().removesuffix(" County").strip()


async def ingest_election_results(
    session: AsyncSession,
    election_id: uuid.UUID,
    feed: SoSFeed,
) -> int:
    """Upsert statewide and county-level election results.

    Args:
        session: Async database session.
        election_id: The UUID of the election to update.
        feed: Parsed SoS feed data.

    Returns:
        Number of county results upserted.
    """
    now = datetime.now(UTC)

    # --- Statewide result upsert ---
    statewide_ballot = feed.results.ballotItems[0] if feed.results.ballotItems else None

    precincts_participating = statewide_ballot.precinctsParticipating if statewide_ballot else None
    precincts_reporting = statewide_ballot.precinctsReporting if statewide_ballot else None
    results_data = [opt.model_dump() for opt in statewide_ballot.ballotOptions] if statewide_ballot else []

    source_created_at = None
    try:
        source_created_at = feed.created_at_dt
    except (ValueError, TypeError):
        logger.warning("Could not parse createdAt from SoS feed: {}", feed.createdAt)

    existing_result = await session.execute(select(ElectionResult).where(ElectionResult.election_id == election_id))
    result_row = existing_result.scalar_one_or_none()

    if result_row is None:
        result_row = ElectionResult(
            election_id=election_id,
            precincts_participating=precincts_participating,
            precincts_reporting=precincts_reporting,
            results_data=results_data,
            source_created_at=source_created_at,
            fetched_at=now,
        )
        session.add(result_row)
    else:
        result_row.precincts_participating = precincts_participating
        result_row.precincts_reporting = precincts_reporting
        result_row.results_data = results_data
        result_row.source_created_at = source_created_at
        result_row.fetched_at = now

    # --- County results upsert ---
    counties_updated = 0

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

        existing_county = await session.execute(
            select(ElectionCountyResult).where(
                ElectionCountyResult.election_id == election_id,
                ElectionCountyResult.county_name == county_name,
            )
        )
        county_row = existing_county.scalar_one_or_none()

        if county_row is None:
            county_row = ElectionCountyResult(
                election_id=election_id,
                county_name=county_name,
                county_name_normalized=county_name_normalized,
                precincts_participating=county_precincts_participating,
                precincts_reporting=county_precincts_reporting,
                results_data=county_results_data,
            )
            session.add(county_row)
        else:
            county_row.precincts_participating = county_precincts_participating
            county_row.precincts_reporting = county_precincts_reporting
            county_row.results_data = county_results_data

        counties_updated += 1

    await session.flush()

    logger.info(
        "Ingested results for election {}: {} counties",
        election_id,
        counties_updated,
    )

    return counties_updated
