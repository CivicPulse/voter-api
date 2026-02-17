"""Voter stats service — aggregate voter registration counts for boundaries."""

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.analyzer import BOUNDARY_TYPE_TO_VOTER_FIELD
from voter_api.models.voter import Voter
from voter_api.schemas.voter_stats import VoterRegistrationStatsResponse, VoterStatusCount


async def get_voter_stats_for_boundary(
    session: AsyncSession,
    boundary_type: str,
    boundary_identifier: str,
    county: str | None = None,
    county_name_override: str | None = None,
) -> VoterRegistrationStatsResponse | None:
    """Get aggregate voter registration stats for a boundary.

    Args:
        session: Database session.
        boundary_type: The boundary type (e.g., "congressional").
        boundary_identifier: The boundary identifier (e.g., "5").
        county: The boundary's county column (for county-scoped districts).
        county_name_override: Override county name for the "county" boundary
            type where boundary_identifier is a FIPS GEOID.

    Returns:
        VoterRegistrationStatsResponse, or None if the boundary type
        has no voter field mapping.
    """
    if boundary_type == "county":
        if not county_name_override:
            logger.debug(
                "No county name override for county boundary {}, "
                "cannot determine voter stats",
                boundary_identifier,
            )
            return None
        query = (
            select(Voter.status, func.count(Voter.id))
            .where(
                func.upper(Voter.county) == func.upper(county_name_override),
                Voter.present_in_latest_import.is_(True),
            )
            .group_by(Voter.status)
        )
    else:
        voter_field = BOUNDARY_TYPE_TO_VOTER_FIELD.get(boundary_type)
        if voter_field is None:
            return None

        voter_column = getattr(Voter, voter_field)
        query = (
            select(Voter.status, func.count(Voter.id))
            .where(
                voter_column == boundary_identifier,
                Voter.present_in_latest_import.is_(True),
            )
            .group_by(Voter.status)
        )

        if county:
            query = query.where(func.upper(Voter.county) == func.upper(county))

    result = await session.execute(query)
    rows = result.all()

    if not rows:
        return VoterRegistrationStatsResponse(total=0, by_status=[])

    by_status = [VoterStatusCount(status=status, count=count) for status, count in rows]
    total = sum(sc.count for sc in by_status)

    return VoterRegistrationStatsResponse(total=total, by_status=by_status)
