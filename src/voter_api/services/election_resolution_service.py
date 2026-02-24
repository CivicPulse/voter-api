"""Election resolution service — link voter history records to elections.

Provides three-tier matching to populate voter_history.election_id:

1. Single-election dates: bulk assign when only one election on a date.
2. District-based matching: use voter district registration to disambiguate
   multi-election dates.
3. Unresolvable: PSC (no voter column), missing voters, or no election for date.

Also provides backfill of structured district fields on elections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select, text

from voter_api.lib.district_parser import (
    DISTRICT_TYPE_TO_BOUNDARY_TYPE,
    DISTRICT_TYPE_TO_VOTER_COLUMN,
    pad_district_identifier,
    parse_election_district,
)
from voter_api.models.boundary import Boundary
from voter_api.models.election import Election

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ResolutionResult:
    """Summary of an election resolution run."""

    tier1_updated: int = 0
    tier2_updated: int = 0
    unresolvable: int = 0
    elections_backfilled: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_updated(self) -> int:
        return self.tier1_updated + self.tier2_updated


async def backfill_election_district_fields(session: AsyncSession) -> int:
    """Parse all elections' district text and populate structured fields + boundary_id.

    Only updates elections that are missing district_type (not yet parsed).

    Args:
        session: Database session.

    Returns:
        Number of elections updated.
    """
    result = await session.execute(select(Election).where(Election.district_type.is_(None)))
    elections = list(result.scalars().all())

    if not elections:
        logger.info("No elections need district field backfill")
        return 0

    updated = 0
    for election in elections:
        if await link_election_to_boundary(session, election):
            updated += 1

    await session.commit()
    logger.info("Backfilled district fields on {} elections", updated)
    return updated


async def link_election_to_boundary(session: AsyncSession, election: Election) -> bool:
    """Parse a single election's district text and set structured fields + boundary_id.

    Args:
        session: Database session.
        election: Election model instance to update.

    Returns:
        True if fields were updated, False if district format unrecognized.
    """
    parsed = parse_election_district(election.district)
    if parsed.district_type is None:
        return False

    election.district_type = parsed.district_type
    election.district_identifier = parsed.district_identifier
    election.district_party = parsed.party

    # Look up boundary by (type, zero-padded identifier)
    if parsed.district_identifier is not None:
        boundary_type = DISTRICT_TYPE_TO_BOUNDARY_TYPE.get(parsed.district_type)
        if boundary_type:
            padded = pad_district_identifier(parsed.district_identifier)
            result = await session.execute(
                select(Boundary.id).where(
                    Boundary.boundary_type == boundary_type,
                    Boundary.boundary_identifier == padded,
                )
            )
            boundary_row = result.first()
            if boundary_row:
                election.boundary_id = boundary_row[0]

    return True


async def resolve_voter_history_elections(
    session: AsyncSession,
    *,
    election_date: date | None = None,
    force: bool = False,
) -> ResolutionResult:
    """Resolve voter_history.election_id using three-tier matching.

    Args:
        session: Database session.
        election_date: Optional date filter. If None, resolves all dates.
        force: If True, re-resolves records that already have election_id.

    Returns:
        ResolutionResult with counts from each tier.
    """
    result = ResolutionResult()

    # First, backfill any elections missing structured fields
    result.elections_backfilled = await backfill_election_district_fields(session)

    # Build election date filter
    election_query = select(
        Election.election_date,
        func.count(Election.id).label("election_count"),
    ).group_by(Election.election_date)

    if election_date:
        election_query = election_query.where(Election.election_date == election_date)

    date_counts = (await session.execute(election_query)).all()

    for edate, count in date_counts:
        if count == 1:
            updated = await _resolve_tier1_single_election(session, edate, force=force)
            result.tier1_updated += updated
        else:
            t2, unresolvable = await _resolve_tier2_district_matching(session, edate, force=force)
            result.tier2_updated += t2
            result.unresolvable += unresolvable

    await session.commit()
    logger.info(
        "Election resolution complete: tier1={}, tier2={}, unresolvable={}",
        result.tier1_updated,
        result.tier2_updated,
        result.unresolvable,
    )
    return result


async def _resolve_tier1_single_election(
    session: AsyncSession,
    election_date: date,
    *,
    force: bool = False,
) -> int:
    """Tier 1: Assign all voter_history records on a single-election date.

    Args:
        session: Database session.
        election_date: The date with exactly one election.
        force: If True, overwrite existing election_id values.

    Returns:
        Number of voter_history records updated.
    """
    election_result = await session.execute(select(Election.id).where(Election.election_date == election_date))
    election_id = election_result.scalar_one()

    if force:
        sql = "UPDATE voter_history SET election_id = :eid WHERE election_date = :edate"
    else:
        sql = "UPDATE voter_history SET election_id = :eid WHERE election_date = :edate AND election_id IS NULL"

    result = await session.execute(text(sql), {"eid": election_id, "edate": election_date})
    updated = result.rowcount
    if updated > 0:
        logger.debug(
            "Tier 1: assigned {} records to election {} on {}",
            updated,
            election_id,
            election_date,
        )
    return updated


async def _resolve_tier2_district_matching(
    session: AsyncSession,
    election_date: date,
    *,
    force: bool = False,
) -> tuple[int, int]:
    """Tier 2: Match voter_history to elections via voter district eligibility.

    For dates with multiple elections, joins voter_history to voters via
    registration number, then matches using the voter's district column.

    Args:
        session: Database session.
        election_date: The date with multiple elections.
        force: If True, overwrite existing election_id values.

    Returns:
        Tuple of (records_updated, elections_unresolvable).
    """
    # Get all elections on this date
    elections_result = await session.execute(select(Election).where(Election.election_date == election_date))
    elections = list(elections_result.scalars().all())

    total_updated = 0
    unresolvable = 0

    # Deduplicate: group by (district_type, district_identifier, district_party)
    seen_keys: dict[tuple[str | None, str | None, str | None], Election] = {}
    for election in elections:
        key = (election.district_type, election.district_identifier, election.district_party)
        if key in seen_keys:
            existing = seen_keys[key]
            # Prefer election with boundary_id set, then shorter name
            if (election.boundary_id and not existing.boundary_id) or (
                not existing.boundary_id and not election.boundary_id and len(election.name) < len(existing.name)
            ):
                seen_keys[key] = election
            logger.warning(
                "Duplicate elections on {}: '{}' and '{}' both parse to ({}, {}, {}). Using '{}'.",
                election_date,
                existing.name,
                election.name,
                *key,
                seen_keys[key].name,
            )
        else:
            seen_keys[key] = election

    for election in seen_keys.values():
        if election.district_type is None or election.district_identifier is None:
            logger.debug(
                "Unresolvable: election '{}' on {} has no parsed district",
                election.name,
                election_date,
            )
            unresolvable += 1
            continue

        voter_column = DISTRICT_TYPE_TO_VOTER_COLUMN.get(election.district_type)
        if voter_column is None:
            logger.debug(
                "Unresolvable: election '{}' ({}) has no voter column mapping",
                election.name,
                election.district_type,
            )
            unresolvable += 1
            continue

        # voter_column comes from a controlled constant (DISTRICT_TYPE_TO_VOTER_COLUMN),
        # not user input — safe to interpolate into SQL.
        updated = await _update_vh_by_district(
            session,
            election_id=election.id,
            election_date=election_date,
            voter_column=voter_column,
            district_identifier=election.district_identifier,
            force=force,
        )
        total_updated += updated
        if updated > 0:
            logger.debug(
                "Tier 2: assigned {} records to '{}' on {} via {}.{}={}",
                updated,
                election.name,
                election_date,
                "voters",
                voter_column,
                election.district_identifier,
            )

    return total_updated, unresolvable


# Allowed voter table columns for district matching.
# Used as a safelist to prevent SQL injection in _update_vh_by_district.
_ALLOWED_VOTER_COLUMNS = frozenset(DISTRICT_TYPE_TO_VOTER_COLUMN.values())


async def _update_vh_by_district(
    session: AsyncSession,
    *,
    election_id: object,
    election_date: date,
    voter_column: str,
    district_identifier: str,
    force: bool,
) -> int:
    """Execute district-based UPDATE of voter_history via JOIN to voters.

    The voter_column parameter is validated against _ALLOWED_VOTER_COLUMNS
    to prevent SQL injection.

    Args:
        session: Database session.
        election_id: Election UUID to assign.
        election_date: Election date filter.
        voter_column: Voter table column name for district matching.
        district_identifier: Unpadded district identifier value.
        force: If True, overwrite existing election_id values.

    Returns:
        Number of voter_history records updated.
    """
    if voter_column not in _ALLOWED_VOTER_COLUMNS:
        msg = f"Invalid voter column: {voter_column}"
        raise ValueError(msg)

    null_filter = "" if force else " AND vh.election_id IS NULL"
    # voter_column is validated against _ALLOWED_VOTER_COLUMNS above
    sql = (
        f"UPDATE voter_history vh SET election_id = :election_id "  # noqa: S608
        f"FROM voters v "
        f"WHERE vh.voter_registration_number = v.voter_registration_number "
        f"AND vh.election_date = :election_date"
        f"{null_filter} "
        f"AND v.{voter_column} = :district_identifier"
    )
    result = await session.execute(
        text(sql),
        {
            "election_id": election_id,
            "election_date": election_date,
            "district_identifier": district_identifier,
        },
    )
    return result.rowcount
