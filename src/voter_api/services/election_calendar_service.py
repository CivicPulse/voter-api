"""Service for importing election calendar dates into existing elections.

Matches calendar entries to existing elections by name and date, then
updates the calendar fields (registration deadline, early voting dates,
qualifying period, etc.).
"""

from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.election_calendar.parser import CalendarEntry
from voter_api.models.election import Election


@dataclass
class CalendarImportResult:
    """Result summary from a calendar import operation.

    Attributes:
        matched: Number of entries that matched an existing election.
        updated: Number of elections that were actually updated.
        unmatched: Number of entries with no matching election.
        unmatched_names: Names of unmatched elections for user feedback.
    """

    matched: int = 0
    updated: int = 0
    unmatched: int = 0
    unmatched_names: list[str] = field(default_factory=list)


async def process_calendar_import(
    session: AsyncSession,
    entries: list[CalendarEntry],
) -> CalendarImportResult:
    """Import calendar dates into existing elections.

    For each ``CalendarEntry``, finds a matching election by ``(name,
    election_date)`` where ``deleted_at IS NULL``. If found, updates
    calendar fields with non-None values from the entry. Does NOT create
    new elections.

    Args:
        session: Active async database session.
        entries: Parsed calendar entries to import.

    Returns:
        Summary of matched, updated, and unmatched entries.
    """
    result = CalendarImportResult()

    for entry in entries:
        # Find matching election
        stmt = select(Election).where(
            Election.name == entry.election_name,
            Election.election_date == entry.election_date,
            Election.deleted_at.is_(None),
        )
        row = await session.execute(stmt)
        election = row.scalar_one_or_none()

        if election is None:
            result.unmatched += 1
            result.unmatched_names.append(f"{entry.election_name} ({entry.election_date})")
            logger.warning(
                "No matching election for calendar entry: {} on {}",
                entry.election_name,
                entry.election_date,
            )
            continue

        result.matched += 1

        # Build update values (only non-None fields)
        _calendar_fields = (
            "registration_deadline",
            "early_voting_start",
            "early_voting_end",
            "absentee_request_deadline",
            "qualifying_start",
            "qualifying_end",
        )
        update_values = {f: getattr(entry, f) for f in _calendar_fields if getattr(entry, f) is not None}

        if not update_values:
            logger.info(
                "Election {} matched but no calendar fields to update",
                election.id,
            )
            continue

        stmt_update = update(Election).where(Election.id == election.id).values(**update_values)
        await session.execute(stmt_update)
        result.updated += 1
        logger.info(
            "Updated election {} ({}) with {} calendar field(s)",
            election.id,
            entry.election_name,
            len(update_values),
        )

    await session.commit()
    return result
