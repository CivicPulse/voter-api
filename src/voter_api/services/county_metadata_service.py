"""County metadata service — manages Census TIGER/Line county attributes."""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.county_metadata import CountyMetadata


async def import_county_metadata(session: AsyncSession, records: list[dict]) -> int:
    """Import county metadata records, upserting by GEOID.

    Args:
        session: Database session.
        records: List of dicts with snake_case column names matching
            CountyMetadata fields (e.g. ``{"geoid": "13121", ...}``).

    Returns:
        Number of records upserted.
    """
    logger.info(f"Importing {len(records)} county metadata records")

    upserted = 0
    for rec in records:
        geoid = rec.get("geoid")
        if not geoid:
            continue

        result = await session.execute(select(CountyMetadata).where(CountyMetadata.geoid == geoid))
        existing = result.scalar_one_or_none()

        if existing:
            for key, value in rec.items():
                if key != "geoid" and hasattr(existing, key):
                    setattr(existing, key, value)
        else:
            session.add(CountyMetadata(**rec))

        upserted += 1

    await session.commit()
    logger.info(f"Upserted {upserted} county metadata records")
    return upserted


async def get_county_metadata_by_geoid(session: AsyncSession, geoid: str) -> CountyMetadata | None:
    """Look up county metadata by FIPS GEOID.

    Args:
        session: Database session.
        geoid: Five-character FIPS GEOID (e.g. "13121").

    Returns:
        CountyMetadata record or None if not found.
    """
    result = await session.execute(select(CountyMetadata).where(CountyMetadata.geoid == geoid))
    return result.scalar_one_or_none()
