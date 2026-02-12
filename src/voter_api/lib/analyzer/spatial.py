"""Spatial analysis — point-in-polygon queries for voter locations.

Given a voter's primary geocoded location, finds all containing
boundaries grouped by boundary type using PostGIS ST_Contains.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.boundary import Boundary
from voter_api.models.geocoded_location import GeocodedLocation


async def find_voter_boundaries(
    session: AsyncSession,
    geocoded_location: GeocodedLocation,
) -> dict[str, str]:
    """Find all boundaries containing a voter's geocoded point.

    Args:
        session: Database session.
        geocoded_location: The voter's primary geocoded location.

    Returns:
        Dict mapping boundary_type to boundary_identifier for all
        boundaries containing the point.
    """
    query = select(Boundary.boundary_type, Boundary.boundary_identifier).where(
        func.ST_Contains(
            Boundary.geometry,
            geocoded_location.point,
        )
    )

    result = await session.execute(query)
    rows = result.all()

    # Group by boundary type — if multiple boundaries of the same type
    # contain the point (boundary-line edge case), use deterministic
    # tie-breaking: lowest boundary_identifier alphabetically
    boundaries: dict[str, list[str]] = {}
    for boundary_type, boundary_identifier in rows:
        boundaries.setdefault(boundary_type, []).append(boundary_identifier)

    determined: dict[str, str] = {}
    for boundary_type, identifiers in boundaries.items():
        identifiers.sort()
        determined[boundary_type] = identifiers[0]

    return determined


async def find_voter_boundaries_batch(
    session: AsyncSession,
    geocoded_locations: list[GeocodedLocation],
) -> dict[str, dict[str, str]]:
    """Find boundaries for a batch of voters.

    Args:
        session: Database session.
        geocoded_locations: List of primary geocoded locations.

    Returns:
        Dict mapping voter_id (str) to their determined boundaries.
    """
    results: dict[str, dict[str, str]] = {}
    for loc in geocoded_locations:
        voter_id_str = str(loc.voter_id)
        results[voter_id_str] = await find_voter_boundaries(session, loc)
    return results
