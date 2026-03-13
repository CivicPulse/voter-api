"""Precinct crosswalk service — CRUD and spatial join builder."""

from loguru import logger
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.precinct_crosswalk import PrecinctCrosswalk


async def get_crosswalk_stats(session: AsyncSession) -> dict:
    """Get summary statistics for the precinct crosswalk table.

    Args:
        session: Database session.

    Returns:
        Dict with total_entries, counties_covered, avg_confidence.
    """
    result = await session.execute(
        select(
            func.count(PrecinctCrosswalk.id).label("total"),
            func.count(func.distinct(PrecinctCrosswalk.county_name)).label("counties"),
            func.avg(PrecinctCrosswalk.confidence).label("avg_confidence"),
        )
    )
    row = result.one()
    return {
        "total_entries": row.total,
        "counties_covered": row.counties,
        "avg_confidence": round(float(row.avg_confidence or 0), 3),
    }


async def upsert_crosswalk_entries(
    session: AsyncSession,
    entries: list[dict],
) -> tuple[int, int]:
    """Upsert precinct crosswalk entries.

    Args:
        session: Database session.
        entries: List of dicts with county_code, county_name, voter_precinct_code,
                 boundary_precinct_identifier, source, confidence.

    Returns:
        Tuple of (inserted, updated) counts.
    """
    if not entries:
        return 0, 0

    inserted = 0
    updated = 0

    for entry in entries:
        stmt = pg_insert(PrecinctCrosswalk.__table__).values(**entry)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_precinct_crosswalk_county_precinct",
            set_={
                "boundary_precinct_identifier": stmt.excluded.boundary_precinct_identifier,
                "source": stmt.excluded.source,
                "confidence": stmt.excluded.confidence,
            },
        )
        # Use RETURNING with xmax to distinguish inserts from updates:
        # xmax = 0 means a genuine insert; nonzero means an update.
        stmt = stmt.returning(literal_column("(xmax = 0)::int").label("is_insert"))  # type: ignore[assignment]
        result = await session.execute(stmt)
        row = result.one()
        if row.is_insert:
            inserted += 1
        else:
            updated += 1

    await session.commit()
    logger.info("Upserted {} crosswalk entries ({} inserted, {} updated)", len(entries), inserted, updated)
    return inserted, updated
