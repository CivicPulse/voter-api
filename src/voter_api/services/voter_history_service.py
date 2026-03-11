"""Voter history service — import, query, and aggregate participation data."""

import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, NamedTuple

from loguru import logger
from sqlalchemy import ColumnElement, Row, and_, delete, exists, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
    ParticipationFilters,
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
        autocommit_conn = await vacuum_conn.execution_options(isolation_level="AUTOCOMMIT")
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
    filters: ParticipationFilters | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[VoterHistory] | list[Row[Any]], int, bool]:
    """List voters who participated in an election.

    Looks up the election by ID to get (date, type), then queries
    voter_history by (election_date, normalized_election_type).

    When voter-table filters are active (q, county_precinct, districts,
    voter_status, has_district_mismatch), JOINs to the voters table and
    returns rows with voter details included (3rd element is True).

    Args:
        session: Database session.
        election_id: Election UUID.
        filters: Optional participation filters bundle.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (records, total count, voter_details_included).
        When voter_details_included is True, each record is a tuple of
        (VoterHistory, voter_id, first_name, last_name, has_district_mismatch).

    Raises:
        ValueError: If election not found.
    """
    if filters is None:
        filters = ParticipationFilters()

    election = await _get_election_or_raise(session, election_id)
    match_conditions = await _build_election_match_conditions(session, election)

    # Normalize q and pre-tokenize; treat non-token queries as empty
    q_terms: list[str] = []
    if filters.q is not None:
        stripped = filters.q.strip()
        q_terms = [w for w in re.split(r"[\s,;.]+", stripped) if w]

    # Determine if we need to JOIN to voters table
    voter_filters_active = any(
        [
            q_terms,
            filters.county_precinct,
            filters.congressional_district,
            filters.state_senate_district,
            filters.state_house_district,
            filters.county_commission_district,
            filters.school_board_district,
            filters.voter_status,
            filters.has_district_mismatch is not None,
        ]
    )

    query: Any
    count_query: Any

    if voter_filters_active:
        # JOIN path: query voter_history + voters in one query
        query = (
            select(
                VoterHistory,
                Voter.id.label("voter_id"),
                Voter.first_name,
                Voter.last_name,
                Voter.has_district_mismatch,
            )
            .outerjoin(Voter, VoterHistory.voter_registration_number == Voter.voter_registration_number)
            .where(*match_conditions)
        )
        count_query = (
            select(func.count(VoterHistory.id))
            .outerjoin(Voter, VoterHistory.voter_registration_number == Voter.voter_registration_number)
            .where(*match_conditions)
        )

        query, count_query = _apply_voter_filters(query, count_query, filters, q_terms)
    else:
        # Default path: query voter_history only
        query = select(VoterHistory).where(*match_conditions)
        count_query = select(func.count(VoterHistory.id)).where(*match_conditions)

    # Apply voter_history filters (common to both paths)
    query, count_query = _apply_history_filters(query, count_query, filters)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(VoterHistory.voter_registration_number).offset(offset).limit(page_size)
    result = await session.execute(query)

    if voter_filters_active:
        rows = list(result.all())
        return rows, total, True

    records = list(result.scalars().all())
    return records, total, False


def _apply_voter_filters(
    query: Any,
    count_query: Any,
    filters: ParticipationFilters,
    q_terms: list[str],
) -> tuple[Any, Any]:
    """Apply voter-table filters and q search to query and count_query.

    Args:
        query: The main SELECT query.
        count_query: The COUNT query.
        filters: Participation filters bundle.
        q_terms: Pre-tokenized search terms (empty list if no search).

    Returns:
        Tuple of (query, count_query) with filters applied.
    """
    if q_terms:
        for word in q_terms:
            word_escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{word_escaped}%"
            word_condition = or_(
                Voter.first_name.ilike(pattern, escape="\\"),
                Voter.last_name.ilike(pattern, escape="\\"),
                Voter.middle_name.ilike(pattern, escape="\\"),
                VoterHistory.voter_registration_number.ilike(pattern, escape="\\"),
            )
            query = query.where(word_condition)
            count_query = count_query.where(word_condition)

    # Map filter fields to Voter model columns
    field_column_pairs: list[tuple[str | None, Any]] = [
        (filters.county_precinct, Voter.county_precinct),
        (filters.congressional_district, Voter.congressional_district),
        (filters.state_senate_district, Voter.state_senate_district),
        (filters.state_house_district, Voter.state_house_district),
        (filters.county_commission_district, Voter.county_commission_district),
        (filters.school_board_district, Voter.school_board_district),
        (filters.voter_status, Voter.status),
    ]
    for value, column in field_column_pairs:
        if value:
            query = query.where(column == value)
            count_query = count_query.where(column == value)

    if filters.has_district_mismatch is not None:
        query = query.where(Voter.has_district_mismatch == filters.has_district_mismatch)
        count_query = count_query.where(Voter.has_district_mismatch == filters.has_district_mismatch)

    return query, count_query


def _apply_history_filters(
    query: Any,
    count_query: Any,
    filters: ParticipationFilters,
) -> tuple[Any, Any]:
    """Apply voter_history-table filters to query and count_query.

    Args:
        query: The main SELECT query.
        count_query: The COUNT query.
        filters: Participation filters bundle.

    Returns:
        Tuple of (query, count_query) with filters applied.
    """
    if filters.county:
        query = query.where(VoterHistory.county == filters.county)
        count_query = count_query.where(VoterHistory.county == filters.county)
    if filters.ballot_style:
        query = query.where(VoterHistory.ballot_style == filters.ballot_style)
        count_query = count_query.where(VoterHistory.ballot_style == filters.ballot_style)
    if filters.absentee is not None:
        query = query.where(VoterHistory.absentee == filters.absentee)
        count_query = count_query.where(VoterHistory.absentee == filters.absentee)
    if filters.provisional is not None:
        query = query.where(VoterHistory.provisional == filters.provisional)
        count_query = count_query.where(VoterHistory.provisional == filters.provisional)
    if filters.supplemental is not None:
        query = query.where(VoterHistory.supplemental == filters.supplemental)
        count_query = count_query.where(VoterHistory.supplemental == filters.supplemental)
    return query, count_query


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

    # Compute eligible voters and turnout percentage from voter registration data
    total_eligible_voters: int | None = None
    turnout_percentage: float | None = None

    if election.district_type and election.district_identifier:
        county_name_override: str | None = None
        if election.district_type == "county" and election.boundary:
            # Strip " County" suffix from boundary name (e.g. "Fulton County" → "Fulton")
            bname = election.boundary.name
            county_name_override = bname.removesuffix(" County") if bname else None

        from voter_api.services.voter_stats_service import get_voter_stats_for_boundary

        voter_stats = await get_voter_stats_for_boundary(
            session,
            election.district_type,
            election.district_identifier,
            county_name_override=county_name_override,
        )
        if voter_stats:
            active_count = sum(sc.count for sc in voter_stats.by_status if sc.status.upper() == "ACTIVE")
            if active_count > 0:
                total_eligible_voters = active_count
                turnout_percentage = round((total_participants / active_count) * 100, 1)

    return ParticipationStatsResponse(
        election_id=election_id,
        total_participants=total_participants,
        total_eligible_voters=total_eligible_voters,
        turnout_percentage=turnout_percentage,
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
    """Lightweight container for voter identity fields resolved from registration numbers.

    Attributes:
        id: Voter UUID primary key.
        first_name: Voter's first name.
        last_name: Voter's last name.
        has_district_mismatch: Whether voter has a district mismatch.
    """

    id: uuid.UUID
    first_name: str
    last_name: str
    has_district_mismatch: bool | None


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
            Voter.has_district_mismatch,
        ).where(Voter.voter_registration_number.in_(unique_nums))
    )
    return {
        row[0]: VoterLookupResult(id=row[1], first_name=row[2], last_name=row[3], has_district_mismatch=row[4])
        for row in result.all()
    }


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

    County scoping: when the election is county-scoped (district_type ==
    "county", or district_type is None but boundary is a county boundary),
    an additional county-name predicate is appended to whichever branch
    applies (both unresolved and the fallback clause inside the resolved OR).
    The predicate compares ``UPPER(VoterHistory.county)`` to the county name
    derived from ``election.boundary.name`` (stripping the " County" suffix).
    This prevents cross-county leakage when county elections share a date
    with other county elections.

    Args:
        session: Database session.
        election: The Election model instance.

    Returns:
        List of SQLAlchemy WHERE clause conditions.
    """

    def _build_district_filter() -> ColumnElement[bool] | None:
        """Return a county filter if election is county-scoped, else None."""
        boundary = election.boundary
        if boundary is None:
            return None

        # Sub-county boundaries (county_commission, school_board, etc.) have an
        # explicit county field — use it when available.
        if boundary.county:
            return func.upper(VoterHistory.county) == boundary.county.upper()

        # County-type boundaries derive county name from boundary name.
        is_county_scoped = election.district_type == "county" or (
            election.district_type is None and boundary.boundary_type == "county"
        )
        if is_county_scoped and boundary.name:
            name = boundary.name
            county_name = name[:-7] if name.lower().endswith(" county") else name
            return func.upper(VoterHistory.county) == county_name.upper()

        return None

    # Check if any voter_history records have been resolved for this election
    has_resolved = await session.execute(select(exists().where(VoterHistory.election_id == election.id)))
    if has_resolved.scalar_one():
        # Include both resolved rows AND still-unresolved rows on the same date.
        # Tier-2 district matching may leave some records with election_id IS NULL
        # (e.g. voters not in the voters table). Scope the fallback to NULL rows
        # only, so we never double-count records already resolved to a different
        # election on the same date.
        count_result = await session.execute(
            select(func.count(Election.id)).where(
                Election.election_date == election.election_date,
            )
        )
        election_count = count_result.scalar_one()
        district_filter = _build_district_filter()  # computed once, shared by both branches

        if election_count == 1:
            # Single-election date: unresolved rows must belong to this election
            fallback_conditions: list[ColumnElement[bool]] = [
                VoterHistory.election_id.is_(None),
                VoterHistory.election_date == election.election_date,
            ]
        else:
            # Multi-election date: use type heuristic + district filter for unresolved rows
            fallback_conditions = [
                VoterHistory.election_id.is_(None),
                VoterHistory.election_date == election.election_date,
                VoterHistory.normalized_election_type == election.election_type,
            ]
        if district_filter is not None:
            fallback_conditions.append(district_filter)
        fallback = and_(*fallback_conditions)

        # Also scope resolved records by county to prevent stale cross-county data leaking
        resolved_condition: ColumnElement[bool] = VoterHistory.election_id == election.id
        if district_filter is not None:
            resolved_condition = and_(resolved_condition, district_filter)
        return [or_(resolved_condition, fallback)]

    # Fallback to date-based heuristic for fully-unresolved records
    count_result = await session.execute(
        select(func.count(Election.id)).where(
            Election.election_date == election.election_date,
        )
    )
    election_count = count_result.scalar_one()

    if election_count == 1:
        conditions: list[ColumnElement[bool]] = [VoterHistory.election_date == election.election_date]
        district_filter = _build_district_filter()
        if district_filter is not None:
            conditions.append(district_filter)
        return conditions

    conditions = [
        VoterHistory.election_date == election.election_date,
        VoterHistory.normalized_election_type == election.election_type,
    ]
    district_filter = _build_district_filter()
    if district_filter is not None:
        conditions.append(district_filter)
    return conditions


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
    result = await session.execute(
        select(Election).options(selectinload(Election.boundary)).where(Election.id == election_id)
    )
    election = result.scalar_one_or_none()
    if election is None:
        msg = f"Election not found: {election_id}"
        raise ValueError(msg)
    return election
