"""Voter history service — import, query, and aggregate participation data."""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NamedTuple

from loguru import logger
from sqlalchemy import ColumnElement, delete, exists, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.database import get_engine
from voter_api.lib.voter_history import (
    parse_voter_history_chunks,
)
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob
from voter_api.models.voter import Voter
from voter_api.models.voter_history import VoterHistory
from voter_api.schemas.voter_history import (
    BallotStyleBreakdown,
    CountyBreakdown,
    ParticipationStatsResponse,
    ParticipationSummary,
    PrecinctBreakdown,
)

# Sub-batch size for voter history upsert: 11 columns * 2000 rows = 22,000 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 2000

# Commit every N chunks to reduce transaction overhead.
# E.g. with batch_size=2000, this commits every 100K records.
_COMMIT_INTERVAL_CHUNKS = 50

# Non-unique indexes to drop before bulk import and rebuild afterward.
# The unique constraint uq_voter_history_participation is kept for ON CONFLICT.
_DROPPABLE_VH_INDEXES: list[dict[str, str]] = [
    {
        "name": "idx_voter_history_reg_num",
        "create": "CREATE INDEX idx_voter_history_reg_num ON voter_history (voter_registration_number)",
    },
    {
        "name": "idx_voter_history_election_date",
        "create": "CREATE INDEX idx_voter_history_election_date ON voter_history (election_date)",
    },
    {
        "name": "idx_voter_history_election_type",
        "create": "CREATE INDEX idx_voter_history_election_type ON voter_history (election_type)",
    },
    {
        "name": "idx_voter_history_county",
        "create": "CREATE INDEX idx_voter_history_county ON voter_history (county)",
    },
    {
        "name": "idx_voter_history_import_job_id",
        "create": "CREATE INDEX idx_voter_history_import_job_id ON voter_history (import_job_id)",
    },
    {
        "name": "idx_voter_history_date_type",
        "create": "CREATE INDEX idx_voter_history_date_type ON voter_history (election_date, normalized_election_type)",
    },
    {
        "name": "idx_voter_history_election_id",
        "create": "CREATE INDEX idx_voter_history_election_id ON voter_history (election_id)",
    },
]


async def _drop_vh_indexes(session: AsyncSession) -> None:
    """Drop non-essential indexes on voter_history before bulk import.

    Args:
        session: Database session.
    """
    for idx in _DROPPABLE_VH_INDEXES:
        await session.execute(text(f"DROP INDEX IF EXISTS {idx['name']}"))
        logger.debug(f"Dropped index: {idx['name']}")
    await session.commit()
    logger.info(f"Dropped {len(_DROPPABLE_VH_INDEXES)} voter_history indexes for bulk import")


async def _rebuild_vh_indexes(session: AsyncSession) -> None:
    """Rebuild voter_history indexes after bulk import.

    Uses elevated maintenance_work_mem for faster index creation.

    Args:
        session: Database session.
    """
    await session.execute(text("SET maintenance_work_mem = '512MB'"))

    for idx in _DROPPABLE_VH_INDEXES:
        create_sql = idx["create"].replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
        logger.info(f"Rebuilding index: {idx['name']}")
        start = time.monotonic()
        await session.execute(text(create_sql))
        elapsed = time.monotonic() - start
        logger.info(f"Rebuilt index {idx['name']} in {elapsed:.1f}s")

    await session.execute(text("RESET maintenance_work_mem"))
    await session.commit()
    logger.info(f"Rebuilt all {len(_DROPPABLE_VH_INDEXES)} voter_history indexes")


async def _disable_vh_autovacuum(session: AsyncSession) -> None:
    """Disable autovacuum on the voter_history table for bulk import.

    Args:
        session: Database session.
    """
    await session.execute(text("ALTER TABLE voter_history SET (autovacuum_enabled = false)"))
    await session.commit()
    logger.info("Disabled autovacuum on voter_history table")


async def _enable_vh_autovacuum_and_vacuum(session: AsyncSession) -> None:
    """Re-enable autovacuum and run VACUUM ANALYZE on voter_history.

    VACUUM cannot run inside a transaction block, so we use the raw
    asyncpg driver connection.

    Args:
        session: Database session.
    """
    await session.execute(text("ALTER TABLE voter_history SET (autovacuum_enabled = true)"))
    await session.commit()
    logger.info("Re-enabled autovacuum on voter_history table")

    logger.info("Running VACUUM ANALYZE on voter_history table...")
    start = time.monotonic()
    engine = get_engine()
    async with engine.connect() as vacuum_conn:
        autocommit_conn = vacuum_conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit_conn.execute(text("VACUUM ANALYZE voter_history"))
    elapsed = time.monotonic() - start
    logger.info(f"VACUUM ANALYZE completed in {elapsed:.1f}s")


@asynccontextmanager
async def bulk_vh_import_context(session: AsyncSession) -> AsyncIterator[None]:
    """Context manager for batch voter history imports.

    Drops indexes and disables autovacuum once on entry, then rebuilds
    indexes and runs VACUUM ANALYZE once on exit (including on error).

    Use this to wrap multiple calls to ``process_voter_history_import`` with
    ``skip_optimizations=True`` so the expensive lifecycle operations
    happen exactly once for the entire batch.

    Args:
        session: Database session for lifecycle DDL operations.

    Yields:
        None — caller processes files inside the context.
    """
    try:
        await session.execute(text("SET synchronous_commit = 'off'"))
        await _disable_vh_autovacuum(session)
        await _drop_vh_indexes(session)
        logger.info("Bulk voter history import context entered: optimizations applied")
        yield
    finally:
        logger.info("Bulk voter history import context exiting: restoring database settings...")
        try:
            await session.rollback()
            await session.execute(text("SET synchronous_commit = 'on'"))
            await _rebuild_vh_indexes(session)
            await _enable_vh_autovacuum_and_vacuum(session)
            logger.info("Bulk voter history import context: database settings restored")
        except Exception:
            logger.exception("Error during bulk VH import teardown — indexes may need manual rebuild")
            raise


async def process_voter_history_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
    batch_size: int = 1000,
    *,
    skip_optimizations: bool = False,
) -> ImportJob:
    """Process a voter history CSV file import.

    Reads the file in chunks, validates records, upserts voter history,
    tracks unmatched voters and duplicates, and handles re-import replacement.

    Performance optimizations applied during import (unless skipped):
    - Drops non-essential indexes, rebuilds after
    - Sets synchronous_commit = off for the session
    - Disables autovacuum, runs VACUUM ANALYZE after

    When ``skip_optimizations=True``, the caller is responsible for
    managing the DB optimization lifecycle (e.g., via ``bulk_vh_import_context``).

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        file_path: Path to the CSV file.
        batch_size: Records per processing batch.
        skip_optimizations: If True, skip index drop/rebuild, autovacuum,
            and synchronous_commit changes. Use when calling within
            ``bulk_vh_import_context``.

    Returns:
        The updated ImportJob with final counts.
    """
    # Cap batch_size to the upsert sub-batch limit so a single chunk never
    # exceeds asyncpg's 32,767 parameter ceiling, regardless of config.
    if batch_size > _UPSERT_SUB_BATCH:
        logger.info(f"Clamping batch_size from {batch_size} to {_UPSERT_SUB_BATCH} (asyncpg parameter limit)")
        batch_size = _UPSERT_SUB_BATCH

    logger.info(f"Starting voter history import: {file_path.name}")

    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()

    total = 0
    succeeded = 0
    failed = 0
    errors: list[dict] = []

    try:
        import_start = time.monotonic()
        if not skip_optimizations:
            logger.info("Applying voter history bulk import optimizations...")
            await session.execute(text("SET synchronous_commit = 'off'"))
            await _disable_vh_autovacuum(session)
            await _drop_vh_indexes(session)
            logger.info("Voter history bulk import optimizations applied")

        for chunk_idx, records in enumerate(parse_voter_history_chunks(file_path, batch_size)):
            chunk_start = time.monotonic()
            chunk_total = len(records)
            total += chunk_total

            valid_records: list[dict] = []
            chunk_failed = 0
            for record in records:
                parse_error = record.pop("_parse_error", None)
                if parse_error:
                    failed += 1
                    chunk_failed += 1
                    errors.append(
                        {
                            "voter_registration_number": record.get("voter_registration_number", "unknown"),
                            "error": parse_error,
                        }
                    )
                    continue

                valid_records.append(record)

            # Batch upsert voter history records
            chunk_succeeded = len(valid_records)
            if valid_records:
                await _upsert_voter_history_batch(session, valid_records, job.id)
                succeeded += chunk_succeeded

            # Flush every chunk to keep data visible in session
            await session.flush()

            # Commit every N chunks to reduce transaction overhead.
            # Duplicates are handled by the DB unique constraint + ON CONFLICT,
            # so re-processing after a crash is safe (idempotent upsert).
            if (chunk_idx + 1) % _COMMIT_INTERVAL_CHUNKS == 0:
                job.last_processed_offset = chunk_idx + 1
                await session.commit()

            chunk_elapsed = time.monotonic() - chunk_start
            logger.info(
                f"Chunk {chunk_idx + 1}: {chunk_total} records "
                f"({chunk_succeeded} valid, {chunk_failed} failed) "
                f"({chunk_elapsed:.1f}s) | running total: {total} records"
            )

        # Update offset to reflect final chunk before the commit
        if total > 0:
            job.last_processed_offset = chunk_idx + 1

        # Final commit for any remaining unflushed work
        await session.commit()

        # Re-import replacement: clean up records from previous imports of same file
        replace_start = time.monotonic()
        await _replace_previous_import(session, job)
        replace_elapsed = time.monotonic() - replace_start
        logger.info(f"Re-import replacement completed in {replace_elapsed:.1f}s")

        # Finalize job
        job.status = "completed"
        job.total_records = total
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.records_inserted = succeeded
        job.records_skipped = 0
        job.records_unmatched = 0
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        import_elapsed = time.monotonic() - import_start
        logger.info(
            f"Voter history import completed in {import_elapsed:.1f}s: {total} total, "
            f"{succeeded} succeeded, {failed} failed"
        )

    except Exception:
        await session.rollback()
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    finally:
        if not skip_optimizations:
            logger.info("Restoring voter history database settings...")
            try:
                await session.rollback()
                await session.execute(text("SET synchronous_commit = 'on'"))
                await _rebuild_vh_indexes(session)
                await _enable_vh_autovacuum_and_vacuum(session)
                logger.info("Voter history database settings restored")
            except Exception:
                logger.exception("Error during VH optimization teardown — indexes may need manual rebuild")

    return job


async def _upsert_voter_history_batch(
    session: AsyncSession,
    records: list[dict],
    import_job_id: uuid.UUID,
) -> None:
    """Batch upsert voter history records using ON CONFLICT.

    On conflict (same voter + date + type), updates the import_job_id
    to the current job, which enables re-import cleanup.

    Args:
        session: Database session.
        records: List of validated record dicts.
        import_job_id: The current import job ID.
    """
    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]
        values = [
            {
                "voter_registration_number": r["voter_registration_number"],
                "county": r["county"],
                "election_date": r["election_date"],
                "election_type": r["election_type"],
                "normalized_election_type": r["normalized_election_type"],
                "party": r.get("party"),
                "ballot_style": r.get("ballot_style"),
                "absentee": r["absentee"],
                "provisional": r["provisional"],
                "supplemental": r["supplemental"],
                "import_job_id": import_job_id,
            }
            for r in batch
        ]

        stmt = pg_insert(VoterHistory).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_voter_history_participation",
            set_={
                "county": stmt.excluded.county,
                "normalized_election_type": stmt.excluded.normalized_election_type,
                "party": stmt.excluded.party,
                "ballot_style": stmt.excluded.ballot_style,
                "absentee": stmt.excluded.absentee,
                "provisional": stmt.excluded.provisional,
                "supplemental": stmt.excluded.supplemental,
                "import_job_id": stmt.excluded.import_job_id,
            },
        )
        await session.execute(stmt)


async def _replace_previous_import(
    session: AsyncSession,
    job: ImportJob,
) -> None:
    """Replace records from previous imports of the same file.

    Finds previous completed import jobs with the same file_name and
    file_type='voter_history', deletes voter_history records still
    associated with those old jobs, and marks old jobs as 'superseded'.

    Args:
        session: Database session.
        job: The current (new) import job.
    """
    # Find previous completed jobs for the same file
    result = await session.execute(
        select(ImportJob).where(
            ImportJob.file_name == job.file_name,
            ImportJob.file_type == "voter_history",
            ImportJob.id != job.id,
            ImportJob.status.in_(["completed", "superseded"]),
        )
    )
    previous_jobs = list(result.scalars().all())

    if not previous_jobs:
        return

    for prev_job in previous_jobs:
        # Delete voter_history records still pointing to the old job
        await session.execute(delete(VoterHistory).where(VoterHistory.import_job_id == prev_job.id))
        prev_job.status = "superseded"
        logger.info(f"Superseded previous import job: {prev_job.id}")

    await session.flush()


async def get_voter_history(
    session: AsyncSession,
    voter_registration_number: str,
    *,
    election_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    county: str | None = None,
    ballot_style: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[VoterHistory], int]:
    """Query a voter's participation history with filtering and pagination.

    Args:
        session: Database session.
        voter_registration_number: Voter registration number.
        election_type: Filter by election type.
        date_from: Filter elections on or after this date.
        date_to: Filter elections on or before this date.
        county: Filter by county name.
        ballot_style: Filter by ballot style.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (records, total count).
    """
    query = select(VoterHistory).where(VoterHistory.voter_registration_number == voter_registration_number)
    count_query = select(func.count(VoterHistory.id)).where(
        VoterHistory.voter_registration_number == voter_registration_number
    )

    if election_type:
        query = query.where(VoterHistory.election_type == election_type)
        count_query = count_query.where(VoterHistory.election_type == election_type)
    if date_from:
        query = query.where(VoterHistory.election_date >= date_from)
        count_query = count_query.where(VoterHistory.election_date >= date_from)
    if date_to:
        query = query.where(VoterHistory.election_date <= date_to)
        count_query = count_query.where(VoterHistory.election_date <= date_to)
    if county:
        query = query.where(VoterHistory.county == county)
        count_query = count_query.where(VoterHistory.county == county)
    if ballot_style:
        query = query.where(VoterHistory.ballot_style == ballot_style)
        count_query = count_query.where(VoterHistory.ballot_style == ballot_style)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(VoterHistory.election_date.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    records = list(result.scalars().all())

    return records, total


async def list_election_participants(
    session: AsyncSession,
    election_id: uuid.UUID,
    *,
    county: str | None = None,
    ballot_style: str | None = None,
    absentee: bool | None = None,
    provisional: bool | None = None,
    supplemental: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[VoterHistory], int]:
    """List voters who participated in an election.

    Looks up the election by ID to get (date, type), then queries
    voter_history by (election_date, normalized_election_type).

    Args:
        session: Database session.
        election_id: Election UUID.
        county: Filter by county.
        ballot_style: Filter by ballot style.
        absentee: Filter by absentee flag.
        provisional: Filter by provisional flag.
        supplemental: Filter by supplemental flag.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (records, total count).

    Raises:
        ValueError: If election not found.
    """
    election = await _get_election_or_raise(session, election_id)
    match_conditions = await _build_election_match_conditions(session, election)

    query = select(VoterHistory).where(*match_conditions)
    count_query = select(func.count(VoterHistory.id)).where(*match_conditions)

    if county:
        query = query.where(VoterHistory.county == county)
        count_query = count_query.where(VoterHistory.county == county)
    if ballot_style:
        query = query.where(VoterHistory.ballot_style == ballot_style)
        count_query = count_query.where(VoterHistory.ballot_style == ballot_style)
    if absentee is not None:
        query = query.where(VoterHistory.absentee == absentee)
        count_query = count_query.where(VoterHistory.absentee == absentee)
    if provisional is not None:
        query = query.where(VoterHistory.provisional == provisional)
        count_query = count_query.where(VoterHistory.provisional == provisional)
    if supplemental is not None:
        query = query.where(VoterHistory.supplemental == supplemental)
        count_query = count_query.where(VoterHistory.supplemental == supplemental)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(VoterHistory.voter_registration_number).offset(offset).limit(page_size)
    result = await session.execute(query)
    records = list(result.scalars().all())

    return records, total


async def get_participation_stats(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> ParticipationStatsResponse:
    """Get aggregate participation statistics for an election.

    Args:
        session: Database session.
        election_id: Election UUID.

    Returns:
        ParticipationStatsResponse with totals and breakdowns.

    Raises:
        ValueError: If election not found.
    """
    election = await _get_election_or_raise(session, election_id)
    base_where = await _build_election_match_conditions(session, election)

    # Total count
    total_result = await session.execute(select(func.count(VoterHistory.id)).where(*base_where))
    total_participants = total_result.scalar_one()

    # By county
    county_result = await session.execute(
        select(VoterHistory.county, func.count(VoterHistory.id))
        .where(*base_where)
        .group_by(VoterHistory.county)
        .order_by(func.count(VoterHistory.id).desc())
    )
    by_county = [CountyBreakdown(county=row[0], count=row[1]) for row in county_result.all()]

    # By ballot style
    style_result = await session.execute(
        select(VoterHistory.ballot_style, func.count(VoterHistory.id))
        .where(*base_where, VoterHistory.ballot_style.is_not(None))
        .group_by(VoterHistory.ballot_style)
        .order_by(func.count(VoterHistory.id).desc())
    )
    by_ballot_style = [BallotStyleBreakdown(ballot_style=row[0], count=row[1]) for row in style_result.all()]

    # By precinct (join to voters table for county_precinct)
    precinct_result = await session.execute(
        select(
            Voter.county_precinct,
            Voter.county_precinct_description,
            func.count(VoterHistory.id),
        )
        .join(Voter, VoterHistory.voter_registration_number == Voter.voter_registration_number)
        .where(*base_where, Voter.county_precinct.is_not(None))
        .group_by(Voter.county_precinct, Voter.county_precinct_description)
        .order_by(func.count(VoterHistory.id).desc())
    )
    by_precinct = [
        PrecinctBreakdown(precinct=row[0], precinct_name=row[1], count=row[2]) for row in precinct_result.all()
    ]

    return ParticipationStatsResponse(
        election_id=election_id,
        total_participants=total_participants,
        by_county=by_county,
        by_ballot_style=by_ballot_style,
        by_precinct=by_precinct,
    )


async def get_participation_summary(
    session: AsyncSession,
    voter_registration_number: str,
) -> ParticipationSummary:
    """Get a lightweight participation summary for a voter.

    Args:
        session: Database session.
        voter_registration_number: The voter's registration number.

    Returns:
        ParticipationSummary with total elections and last election date.
    """
    result = await session.execute(
        select(
            func.count(VoterHistory.id),
            func.max(VoterHistory.election_date),
        ).where(VoterHistory.voter_registration_number == voter_registration_number)
    )
    row = result.one()
    return ParticipationSummary(
        total_elections=row[0],
        last_election_date=row[1],
    )


async def resolve_election_ids(
    session: AsyncSession,
    records: list[VoterHistory],
) -> dict[tuple[date, str], uuid.UUID]:
    """Resolve election IDs for a list of voter history records.

    Uses the same matching logic as _build_election_match_conditions:
    - When only one election exists on a date, matches by date alone.
    - When multiple elections share a date, matches by (date, election_type).

    Args:
        session: Database session.
        records: Voter history records to resolve.

    Returns:
        Mapping from (election_date, normalized_election_type) to Election.id.
    """
    if not records:
        return {}

    record_keys = {(r.election_date, r.normalized_election_type) for r in records}
    unique_dates = {d for d, _ in record_keys}

    result = await session.execute(
        select(Election.id, Election.election_date, Election.election_type).where(
            Election.election_date.in_(unique_dates)
        )
    )
    elections_by_date: dict[date, list[tuple[uuid.UUID, str]]] = {}
    for eid, edate, etype in result.all():
        elections_by_date.setdefault(edate, []).append((eid, etype))

    lookup: dict[tuple[date, str], uuid.UUID] = {}
    for edate, elections in elections_by_date.items():
        if len(elections) == 1:
            election_id = elections[0][0]
            lookup.update({k: election_id for k in record_keys if k[0] == edate})
        else:
            lookup.update({(edate, etype): eid for eid, etype in elections})

    return lookup


class VoterLookupResult(NamedTuple):
    """Lightweight container for voter identity fields resolved from registration numbers."""

    id: uuid.UUID
    first_name: str
    last_name: str


async def lookup_voter_details(
    session: AsyncSession,
    registration_numbers: list[str],
) -> dict[str, VoterLookupResult]:
    """Batch-resolve voter registration numbers to voter identity details.

    Args:
        session: Database session.
        registration_numbers: Voter registration numbers to look up.

    Returns:
        Mapping from voter_registration_number to VoterLookupResult.
    """
    if not registration_numbers:
        return {}

    unique_nums = list(set(registration_numbers))
    result = await session.execute(
        select(
            Voter.voter_registration_number,
            Voter.id,
            Voter.first_name,
            Voter.last_name,
        ).where(Voter.voter_registration_number.in_(unique_nums))
    )
    return {row[0]: VoterLookupResult(id=row[1], first_name=row[2], last_name=row[3]) for row in result.all()}


async def _build_election_match_conditions(
    session: AsyncSession,
    election: Election,
) -> list[ColumnElement[bool]]:
    """Build WHERE conditions to match voter_history records to an election.

    Primary match: uses persisted election_id FK when records have been
    resolved via the election resolution service.

    Fallback: when no resolved records exist for this election, falls back
    to date-based matching. When only one election exists on a given date,
    matches by date alone. When multiple elections share the same date,
    matches by (date, normalized_election_type) for disambiguation.

    Args:
        session: Database session.
        election: The Election model instance.

    Returns:
        List of SQLAlchemy WHERE clause conditions.
    """
    # Check if any voter_history records have been resolved for this election
    has_resolved = await session.execute(select(exists().where(VoterHistory.election_id == election.id)))
    if has_resolved.scalar_one():
        return [VoterHistory.election_id == election.id]

    # Fallback to date-based heuristic for unresolved records
    count_result = await session.execute(
        select(func.count(Election.id)).where(
            Election.election_date == election.election_date,
        )
    )
    election_count = count_result.scalar_one()

    if election_count == 1:
        return [VoterHistory.election_date == election.election_date]

    return [
        VoterHistory.election_date == election.election_date,
        VoterHistory.normalized_election_type == election.election_type,
    ]


async def _get_election_or_raise(
    session: AsyncSession,
    election_id: uuid.UUID,
) -> Election:
    """Get an election by ID or raise ValueError.

    Args:
        session: Database session.
        election_id: Election UUID.

    Returns:
        The Election model instance.

    Raises:
        ValueError: If election not found.
    """
    result = await session.execute(select(Election).where(Election.id == election_id))
    election = result.scalar_one_or_none()
    if election is None:
        msg = f"Election not found: {election_id}"
        raise ValueError(msg)
    return election
