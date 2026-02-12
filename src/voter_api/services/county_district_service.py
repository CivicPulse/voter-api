"""County-district service — manages county-to-district mapping data."""

from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.boundary_loader import parse_county_districts_csv
from voter_api.models.county_district import CountyDistrict


async def import_county_districts(session: AsyncSession, file_path: Path) -> int:
    """Import county-to-district mappings from a CSV file.

    Upserts records — existing mappings are skipped, new ones are inserted.

    Args:
        session: Database session.
        file_path: Path to the county-districts CSV file.

    Returns:
        Number of records inserted.
    """
    records = parse_county_districts_csv(file_path)
    logger.info(f"Importing {len(records)} county-district mappings")

    inserted = 0
    for rec in records:
        result = await session.execute(
            select(CountyDistrict).where(
                CountyDistrict.county_name == rec.county_name,
                CountyDistrict.boundary_type == rec.boundary_type,
                CountyDistrict.district_identifier == rec.district_identifier,
            )
        )
        if result.scalar_one_or_none() is None:
            session.add(
                CountyDistrict(
                    county_name=rec.county_name,
                    boundary_type=rec.boundary_type,
                    district_identifier=rec.district_identifier,
                )
            )
            inserted += 1

    await session.commit()
    logger.info(f"Inserted {inserted} new county-district mappings ({len(records) - inserted} already existed)")
    return inserted
