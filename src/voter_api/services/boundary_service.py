"""Boundary service — orchestrates boundary import, queries, and spatial operations."""

import uuid
from pathlib import Path

from geoalchemy2.shape import from_shape
from loguru import logger
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.boundary_loader import load_boundaries
from voter_api.models.boundary import Boundary
from voter_api.models.county_district import CountyDistrict


def _county_geometry_subquery(county_name: str):
    """Build a scalar subquery returning the geometry of a named county boundary.

    Used as a spatial fallback for boundary types not covered by the
    county_districts relation table.

    Args:
        county_name: County name to look up (e.g., "Bibb", "Fulton").

    Returns:
        A scalar subquery yielding the county's MULTIPOLYGON geometry,
        or NULL if no matching county boundary exists.
    """
    return (
        select(Boundary.geometry)
        .where(
            Boundary.boundary_type == "county",
            func.upper(Boundary.name) == func.upper(county_name),
        )
        .limit(1)
        .scalar_subquery()
    )


def _build_county_filter(county_name: str):
    """Build a hybrid county filter combining relation table, column, and spatial lookups.

    Four-tier OR filter:
    1. Relation table — matches boundaries via county_districts mapping
    2. Direct column — matches boundaries with county column set
    3. County self-match — matches the county boundary itself by name
    4. Spatial fallback — ST_Intersects for boundaries not matched by the relation table

    Args:
        county_name: County name to filter by.

    Returns:
        A SQLAlchemy filter clause.
    """
    upper_county = func.upper(county_name)

    # 1. Relation table: boundary exists in county_districts for this county
    relation_match = exists(
        select(CountyDistrict.id).where(
            func.upper(CountyDistrict.county_name) == upper_county,
            CountyDistrict.boundary_type == Boundary.boundary_type,
            CountyDistrict.district_identifier == Boundary.boundary_identifier,
        )
    )

    # 2. Direct column: boundary has county column set to this county
    column_match = func.upper(Boundary.county) == upper_county

    # 3. County self-match: the county boundary itself
    county_self_match = and_(
        Boundary.boundary_type == "county",
        func.upper(Boundary.name) == upper_county,
    )

    # 4. Spatial fallback: for boundaries not matched by the relation table
    county_geom = _county_geometry_subquery(county_name)
    spatial_fallback = and_(
        Boundary.county.is_(None),
        Boundary.boundary_type != "county",
        ~relation_match,
        func.ST_Intersects(Boundary.geometry, county_geom),
    )

    return or_(relation_match, column_match, county_self_match, spatial_fallback)


async def import_boundaries(
    session: AsyncSession,
    file_path: Path,
    boundary_type: str,
    source: str,
    county: str | None = None,
) -> list[Boundary]:
    """Import boundaries from a file, upserting by type+identifier+county.

    Args:
        session: Database session.
        file_path: Path to shapefile or GeoJSON file.
        boundary_type: Type of boundary (e.g., congressional, county_precinct).
        source: Data source ("state" or "county").
        county: County name for county-level boundaries.

    Returns:
        List of imported/updated Boundary records.
    """
    boundary_data = load_boundaries(file_path)

    logger.info(f"Importing {len(boundary_data)} boundaries (type={boundary_type}, source={source})")

    imported: list[Boundary] = []

    for bd in boundary_data:
        geom_wkb = from_shape(bd.geometry, srid=4326)

        # Extract county from properties when caller doesn't supply one
        effective_county = county
        if effective_county is None and bd.properties:
            effective_county = bd.properties.get("CTYNAME") or bd.properties.get("COUNTY")

        # Check for existing boundary (upsert)
        result = await session.execute(
            select(Boundary).where(
                Boundary.boundary_type == boundary_type,
                Boundary.boundary_identifier == bd.boundary_identifier,
                Boundary.county == effective_county if effective_county else Boundary.county.is_(None),
            )
        )
        existing = result.scalar_one_or_none()

        # Fallback: check for legacy record with NULL county (pre-migration)
        if existing is None and effective_county is not None:
            fallback_result = await session.execute(
                select(Boundary).where(
                    Boundary.boundary_type == boundary_type,
                    Boundary.boundary_identifier == bd.boundary_identifier,
                    Boundary.county.is_(None),
                )
            )
            existing = fallback_result.scalar_one_or_none()

        if existing:
            existing.name = bd.name
            existing.geometry = geom_wkb
            existing.properties = bd.properties
            existing.source = source
            if effective_county:
                existing.county = effective_county
            imported.append(existing)
        else:
            boundary = Boundary(
                name=bd.name,
                boundary_type=boundary_type,
                boundary_identifier=bd.boundary_identifier,
                source=source,
                county=effective_county,
                geometry=geom_wkb,
                properties=bd.properties,
            )
            session.add(boundary)
            imported.append(boundary)

    await session.commit()

    # Import precinct metadata for county_precinct boundaries
    if boundary_type == "county_precinct":
        from voter_api.services.precinct_metadata_service import upsert_precinct_metadata

        meta_count = 0
        for b in imported:
            if b.properties:
                result = await upsert_precinct_metadata(session, b.id, b.properties)
                if result:
                    meta_count += 1
        await session.commit()
        logger.info(f"Upserted {meta_count} precinct metadata records")

    logger.info(f"Imported {len(imported)} boundaries")
    return imported


async def list_boundaries(
    session: AsyncSession,
    *,
    boundary_type: str | None = None,
    county: str | None = None,
    source: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Boundary], int]:
    """List boundaries with optional filters.

    Args:
        session: Database session.
        boundary_type: Filter by boundary type.
        county: Filter by county using hybrid approach (relation table + spatial).
        source: Filter by source.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (boundaries, total count).
    """
    query = select(Boundary)
    count_query = select(func.count(Boundary.id))

    if boundary_type:
        query = query.where(Boundary.boundary_type == boundary_type)
        count_query = count_query.where(Boundary.boundary_type == boundary_type)
    if county:
        county_filter = _build_county_filter(county)
        query = query.where(county_filter)
        count_query = count_query.where(county_filter)
    if source:
        query = query.where(Boundary.source == source)
        count_query = count_query.where(Boundary.source == source)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(Boundary.boundary_type, Boundary.name).offset(offset).limit(page_size)
    result = await session.execute(query)
    boundaries = list(result.scalars().all())

    return boundaries, total


async def list_boundary_types(session: AsyncSession) -> list[str]:
    """Return distinct boundary_type values, sorted alphabetically."""
    result = await session.execute(select(Boundary.boundary_type).distinct().order_by(Boundary.boundary_type))
    return list(result.scalars().all())


async def get_boundary(session: AsyncSession, boundary_id: uuid.UUID) -> Boundary | None:
    """Get a boundary by ID."""
    result = await session.execute(select(Boundary).where(Boundary.id == boundary_id))
    return result.scalar_one_or_none()


async def find_containing_boundaries(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    boundary_type: str | None = None,
    county: str | None = None,
) -> list[Boundary]:
    """Find all boundaries containing a given point (point-in-polygon).

    Args:
        session: Database session.
        latitude: WGS84 latitude.
        longitude: WGS84 longitude.
        boundary_type: Optional filter by boundary type.
        county: Optional filter by county using hybrid approach.

    Returns:
        List of boundaries containing the point.
    """
    point_wkt = f"SRID=4326;POINT({longitude} {latitude})"

    query = select(Boundary).where(func.ST_Contains(Boundary.geometry, func.ST_GeomFromEWKT(point_wkt)))

    if boundary_type:
        query = query.where(Boundary.boundary_type == boundary_type)

    if county:
        query = query.where(_build_county_filter(county))

    result = await session.execute(query)
    return list(result.scalars().all())


async def detect_overlapping_boundaries(
    session: AsyncSession,
    boundary_type: str,
    county: str | None = None,
) -> list[tuple[Boundary, Boundary]]:
    """Detect overlapping boundaries of the same type for admin review.

    Args:
        session: Database session.
        boundary_type: Boundary type to check.
        county: Optional county filter.

    Returns:
        List of overlapping boundary pairs.
    """
    b1 = Boundary.__table__.alias("b1")
    b2 = Boundary.__table__.alias("b2")

    query = select(b1.c.id, b2.c.id).where(
        b1.c.boundary_type == boundary_type,
        b2.c.boundary_type == boundary_type,
        b1.c.id < b2.c.id,
        func.ST_Overlaps(b1.c.geometry, b2.c.geometry),
    )

    if county:
        query = query.where(b1.c.county == county, b2.c.county == county)

    result = await session.execute(query)
    pairs = result.all()

    overlapping: list[tuple[Boundary, Boundary]] = []
    for id1, id2 in pairs:
        boundary1 = await get_boundary(session, id1)
        boundary2 = await get_boundary(session, id2)
        if boundary1 and boundary2:
            overlapping.append((boundary1, boundary2))

    return overlapping
