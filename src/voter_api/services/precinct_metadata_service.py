"""Precinct metadata service — manages GA SoS precinct shapefile attributes."""

import uuid
from decimal import Decimal, InvalidOperation

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.precinct_metadata import PrecinctMetadata

# Mapping from GA SoS precinct shapefile column names to PrecinctMetadata fields.
_PRECINCT_FIELD_MAP: dict[str, str] = {
    "DISTRICT": "sos_district_id",
    "CTYSOSID": "sos_id",
    "FIPS": "fips",
    "FIPS2": "fips_county",
    "CTYNAME": "county_name",
    "CONTY": "county_number",
    "PRECINCT_I": "precinct_id",
    "PRECINCT_N": "precinct_name",
    "AREA": "area",
}


def _extract_precinct_fields(properties: dict) -> dict:
    """Extract and map precinct metadata fields from a shapefile properties dict.

    Args:
        properties: Raw shapefile properties (uppercase column names).

    Returns:
        Dict with snake_case PrecinctMetadata field names.
    """
    result: dict = {}
    for shp_col, meta_field in _PRECINCT_FIELD_MAP.items():
        val = properties.get(shp_col)
        if val is not None:
            if meta_field == "area":
                try:
                    val = Decimal(str(val))
                except (InvalidOperation, ValueError):
                    val = None
            else:
                val = str(val).strip()
            if val is not None:
                result[meta_field] = val
    return result


async def upsert_precinct_metadata(
    session: AsyncSession,
    boundary_id: uuid.UUID,
    properties: dict,
) -> PrecinctMetadata | None:
    """Extract precinct metadata from properties and upsert by boundary_id.

    Args:
        session: Database session.
        boundary_id: FK to the boundaries table.
        properties: Raw shapefile properties dict.

    Returns:
        The upserted PrecinctMetadata record, or None if required fields are missing.
    """
    fields = _extract_precinct_fields(properties)

    # Require the NOT NULL fields
    required = ("sos_district_id", "fips", "fips_county", "county_name", "precinct_id", "precinct_name")
    if not all(fields.get(f) for f in required):
        logger.debug(f"Skipping precinct metadata for boundary {boundary_id}: missing required fields")
        return None

    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id == boundary_id))
    existing = result.scalar_one_or_none()

    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing

    record = PrecinctMetadata(boundary_id=boundary_id, **fields)
    session.add(record)
    return record


async def get_precinct_metadata_batch(
    session: AsyncSession,
    boundary_ids: list[uuid.UUID],
) -> dict[uuid.UUID, PrecinctMetadata]:
    """Look up precinct metadata for multiple boundaries in a single query.

    Args:
        session: Database session.
        boundary_ids: List of boundary UUIDs to look up.

    Returns:
        Dict mapping boundary_id to PrecinctMetadata record.
        Boundaries without metadata are omitted from the result.
    """
    if not boundary_ids:
        return {}

    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id.in_(boundary_ids)))
    return {record.boundary_id: record for record in result.scalars().all()}


async def get_precinct_metadata_by_county_and_ids(
    session: AsyncSession,
    county_name: str,
    precinct_ids: list[str],
) -> dict[str, PrecinctMetadata]:
    """Look up precinct metadata by county name and precinct IDs.

    Args:
        session: Database session.
        county_name: County name to match (case-insensitive).
        precinct_ids: List of precinct IDs to look up (matched uppercase).

    Returns:
        Dict mapping uppercased precinct_id to PrecinctMetadata record.
    """
    if not precinct_ids:
        return {}

    upper_ids = [pid.upper() for pid in precinct_ids]
    result = await session.execute(
        select(PrecinctMetadata).where(
            func.upper(PrecinctMetadata.county_name) == county_name.upper(),
            func.upper(PrecinctMetadata.precinct_id).in_(upper_ids),
        )
    )
    return {record.precinct_id.upper(): record for record in result.scalars().all()}


async def get_precinct_metadata_by_boundary(
    session: AsyncSession,
    boundary_id: uuid.UUID,
) -> PrecinctMetadata | None:
    """Look up precinct metadata by boundary FK.

    Args:
        session: Database session.
        boundary_id: The boundary UUID to look up.

    Returns:
        PrecinctMetadata record or None if not found.
    """
    result = await session.execute(select(PrecinctMetadata).where(PrecinctMetadata.boundary_id == boundary_id))
    return result.scalar_one_or_none()
