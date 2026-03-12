"""Election resolution service — link voter history records to elections.

Provides four-tier matching to populate voter_history fields:

0. Event-level matching: assign election_event_id by (date, type).
1. Single-election dates: bulk assign election_id when only one election on a date.
2. District-based matching: use voter district registration to disambiguate
   multi-election dates.
3. Unresolvable: PSC (no voter column), missing voters, or no election for date.

Also provides backfill of structured district fields on elections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from voter_api.lib.district_parser import (
    DISTRICT_TYPE_TO_BOUNDARY_TYPE,
    DISTRICT_TYPE_TO_VOTER_COLUMN,
    PSC_DISTRICT_COUNTIES,
    pad_district_identifier,
    parse_election_district,
)
from voter_api.models.boundary import Boundary
from voter_api.models.election import Election
from voter_api.models.election_event import ElectionEvent
from voter_api.models.voter_history import VoterHistory

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ResolutionResult:
    """Summary of an election resolution run."""

    tier0_updated: int = 0
    tier1_updated: int = 0
    tier2_updated: int = 0
    unresolvable: int = 0
    elections_backfilled: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_updated(self) -> int:
        return self.tier0_updated + self.tier1_updated + self.tier2_updated


async def find_or_create_election_event(
    session: AsyncSession,
    *,
    event_date: date,
    event_type: str,
    event_name: str | None = None,
) -> uuid.UUID:
    """Find or create an ElectionEvent by (event_date, event_type).

    Uses INSERT ... ON CONFLICT DO NOTHING + a follow-up SELECT for
    idempotent upsert without race conditions.

    Args:
        session: Database session.
        event_date: The election day date.
        event_type: Normalized election type (e.g. "general", "primary").
        event_name: Optional human-readable name. Defaults to
            "{event_type} {event_date}" if not provided.

    Returns:
        UUID of the existing or newly created ElectionEvent.
    """
    if event_name is None:
        event_name = f"{event_type.title()} {event_date}"

    stmt = (
        pg_insert(ElectionEvent.__table__)
        .values(
            event_date=event_date,
            event_type=event_type,
            event_name=event_name,
        )
        .on_conflict_do_nothing(constraint="uq_election_event_date_type")
    )
    await session.execute(stmt)
    await session.flush()

    # Fetch the id (whether just inserted or already existing)
    result = await session.execute(
        select(ElectionEvent.id).where(
            ElectionEvent.event_date == event_date,
            ElectionEvent.event_type == event_type,
        )
    )
    return result.scalar_one()


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

    await session.flush()
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

    # Look up boundary by (type, zero-padded identifier), scoped by county when known
    if parsed.district_identifier is not None:
        boundary_type = DISTRICT_TYPE_TO_BOUNDARY_TYPE.get(parsed.district_type)
        if boundary_type:
            padded = pad_district_identifier(parsed.district_identifier)
            stmt = select(Boundary.id).where(
                Boundary.boundary_type == boundary_type,
                Boundary.boundary_identifier == padded,
            )
            if parsed.county:
                county = parsed.county.strip()
                stmt = stmt.where(func.upper(Boundary.county) == county.upper())
            result = await session.execute(stmt)
            boundary_row = result.first()
            if boundary_row:
                election.boundary_id = boundary_row[0]

    return True


async def resolve_voter_history_elections(
    session: AsyncSession,
    *,
    election_date: date | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> ResolutionResult:
    """Resolve voter_history election fields using four-tier matching.

    Tier 0: Assign election_event_id by (date, normalized_election_type).
    Tier 1: Assign election_id on single-election dates.
    Tier 2: Assign election_id via voter district matching on multi-election dates.

    Args:
        session: Database session.
        election_date: Optional date filter. If None, resolves all dates.
        force: If True, re-resolves records that already have election_id.
        dry_run: If True, flush changes to get accurate counts but roll
            back instead of committing.

    Returns:
        ResolutionResult with counts from each tier.
    """
    result = ResolutionResult()

    # First, backfill any elections missing structured fields
    result.elections_backfilled = await backfill_election_district_fields(session)

    # Tier 0: event-level matching (by date + type)
    result.tier0_updated = await _resolve_tier0_event_matching(session, election_date=election_date, force=force)

    # Build election date filter for Tier 1/2
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

    if dry_run:
        await session.rollback()
    else:
        await session.commit()
    logger.info(
        "Election resolution complete: tier0={}, tier1={}, tier2={}, unresolvable={}",
        result.tier0_updated,
        result.tier1_updated,
        result.tier2_updated,
        result.unresolvable,
    )
    return result


async def _resolve_tier0_event_matching(
    session: AsyncSession,
    *,
    election_date: date | None = None,
    force: bool = False,
) -> int:
    """Tier 0: Assign election_event_id to voter_history by (date, type).

    For each unique (election_date, normalized_election_type) combination
    in voter_history, find or create an ElectionEvent and bulk-assign
    all matching records.

    Args:
        session: Database session.
        election_date: Optional date filter.
        force: If True, overwrite existing election_event_id values.

    Returns:
        Total number of voter_history records updated.
    """
    # Find distinct (date, type) combinations needing resolution
    distinct_query = select(
        VoterHistory.election_date,
        VoterHistory.normalized_election_type,
    ).distinct()

    if election_date:
        distinct_query = distinct_query.where(VoterHistory.election_date == election_date)
    if not force:
        distinct_query = distinct_query.where(VoterHistory.election_event_id.is_(None))

    date_types = (await session.execute(distinct_query)).all()

    if not date_types:
        logger.info("Tier 0: no voter_history records need event-level resolution")
        return 0

    total_updated = 0
    for vh_date, vh_type in date_types:
        # Find or create the event
        event_id = await find_or_create_election_event(
            session,
            event_date=vh_date,
            event_type=vh_type,
        )

        # Bulk update voter_history
        stmt = (
            update(VoterHistory)
            .where(
                VoterHistory.election_date == vh_date,
                VoterHistory.normalized_election_type == vh_type,
            )
            .values(election_event_id=event_id)
        )
        if not force:
            stmt = stmt.where(VoterHistory.election_event_id.is_(None))

        cursor = await session.execute(stmt)
        updated: int = cursor.rowcount  # type: ignore[attr-defined]
        total_updated += updated

        if updated > 0:
            logger.debug(
                "Tier 0: assigned {} records to event {} ({} {})",
                updated,
                event_id,
                vh_date,
                vh_type,
            )

    # Also backfill election_event_id on elections table
    await _backfill_election_event_ids(session)

    await session.flush()
    logger.info("Tier 0: assigned {} voter_history records to election events", total_updated)
    return total_updated


async def _backfill_election_event_ids(session: AsyncSession) -> None:
    """Backfill election_event_id on elections that don't have one yet.

    Matches elections to existing election_events by (election_date, election_type).
    """
    elections_result = await session.execute(select(Election).where(Election.election_event_id.is_(None)))
    elections = list(elections_result.scalars().all())

    for election in elections:
        # Look up the event by date + type
        event_result = await session.execute(
            select(ElectionEvent.id).where(
                ElectionEvent.event_date == election.election_date,
                ElectionEvent.event_type == election.election_type,
            )
        )
        event_id = event_result.scalar_one_or_none()
        if event_id:
            election.election_event_id = event_id

    if elections:
        await session.flush()


async def _resolve_tier1_single_election(
    session: AsyncSession,
    election_date: date,
    *,
    force: bool = False,
) -> int:
    """Tier 1: Assign all voter_history records on a single-election date.

    When the election is linked to a boundary with a county field (sub-county
    types like county_commission), only assigns records from that county.
    This prevents cross-county leakage when other counties have untracked
    elections on the same date.

    Args:
        session: Database session.
        election_date: The date with exactly one election.
        force: If True, overwrite existing election_id values.

    Returns:
        Number of voter_history records updated.
    """
    # Fetch only the fields needed to compute county_name in a single query
    # via outer join — avoids the extra SELECT that selectinload would issue.
    row = (
        await session.execute(
            select(
                Election.id,
                Election.district_type,
                Boundary.county,
                Boundary.boundary_type,
                Boundary.name,
            )
            .outerjoin(Boundary, Election.boundary_id == Boundary.id)
            .where(Election.election_date == election_date)
        )
    ).one()

    election_id, district_type, b_county, b_boundary_type, b_name = row

    stmt = update(VoterHistory).where(VoterHistory.election_date == election_date).values(election_id=election_id)
    if not force:
        stmt = stmt.where(VoterHistory.election_id.is_(None))

    # Scope to county to prevent cross-county assignment.
    # Sub-county boundaries carry county in boundary.county;
    # county-type boundaries carry it in boundary.name (e.g. "Bibb County").
    # Strip whitespace from boundary strings to guard against incidental spaces.
    county_name: str | None = None
    if b_county:
        county_name = b_county.strip()
    elif (b_boundary_type == "county" or district_type == "county") and b_name:
        name = b_name.strip()
        county_name = name[:-7] if name.lower().endswith(" county") else name
    if county_name:
        stmt = stmt.where(func.upper(func.trim(VoterHistory.county)) == county_name.upper())

    cursor = await session.execute(stmt)
    updated: int = cursor.rowcount  # type: ignore[attr-defined]
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

        if voter_column is None and election.district_type == "psc":
            # PSC districts have no voter column — resolve via county membership.
            counties = PSC_DISTRICT_COUNTIES.get(election.district_identifier, [])
            if not counties:
                logger.debug(
                    "Unresolvable: PSC election '{}' has unknown district '{}'",
                    election.name,
                    election.district_identifier,
                )
                unresolvable += 1
                continue

            updated = await _update_vh_by_psc_county(
                session,
                election_id=election.id,
                election_date=election_date,
                counties=counties,
                force=force,
            )
            total_updated += updated
            if updated > 0:
                logger.debug(
                    "Tier 2 (PSC): assigned {} records to '{}' on {} via county membership ({} counties)",
                    updated,
                    election.name,
                    election_date,
                    len(counties),
                )
            continue

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
    election_id: uuid.UUID,
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

    # Generate padded variants of numeric identifiers to handle zero-padding
    # mismatches between election district text and voter CSV fields.
    # Same strategy as voter_stats_service.get_voter_stats_for_boundary.
    if district_identifier.isdigit():
        num_val = int(district_identifier)
        district_ids = list(  # NOSONAR - set literal used for deduplication
            {
                district_identifier,
                str(num_val),
                str(num_val).zfill(2),
                str(num_val).zfill(3),
                str(num_val).zfill(4),
            }
        )
    else:
        district_ids = [district_identifier]

    null_filter = "" if force else "AND vh.election_id IS NULL "
    # voter_column is validated against _ALLOWED_VOTER_COLUMNS above
    sql = (
        f"UPDATE voter_history vh SET election_id = :election_id "  # noqa: S608
        f"FROM voters v "
        f"WHERE vh.voter_registration_number = v.voter_registration_number "
        f"AND vh.election_date = :election_date "
        f"{null_filter}"
        f"AND v.{voter_column} = ANY(:district_ids)"
    )
    cursor = await session.execute(
        text(sql),
        {
            "election_id": election_id,
            "election_date": election_date,
            "district_ids": district_ids,
        },
    )
    return cursor.rowcount  # type: ignore[attr-defined, no-any-return]


async def _update_vh_by_psc_county(
    session: AsyncSession,
    *,
    election_id: uuid.UUID,
    election_date: date,
    counties: list[str],
    force: bool,
) -> int:
    """Update voter_history records for a PSC election via county membership.

    PSC districts don't have a voter table column. Instead, we match
    voter_history records whose county falls within the PSC district's
    county list.

    Args:
        session: Database session.
        election_id: Election UUID to assign.
        election_date: Election date filter.
        counties: List of county names in the PSC district.
        force: If True, overwrite existing election_id values.

    Returns:
        Number of voter_history records updated.
    """
    # Upper-case county names for case-insensitive matching against
    # voter_history.county (which may have varying case).
    upper_counties = [c.upper() for c in counties]

    stmt = (
        update(VoterHistory)
        .where(
            VoterHistory.election_date == election_date,
            func.upper(func.trim(VoterHistory.county)).in_(upper_counties),
        )
        .values(election_id=election_id)
    )
    if not force:
        stmt = stmt.where(VoterHistory.election_id.is_(None))

    cursor = await session.execute(stmt)
    return cursor.rowcount  # type: ignore[attr-defined, no-any-return]
