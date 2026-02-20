"""Import service — orchestrates voter file import with upsert, soft-delete, and diff tracking."""

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dateutil.parser import parse as parse_date
from loguru import logger
from sqlalchemy import literal_column, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.database import get_engine
from voter_api.lib.importer import parse_csv_chunks, validate_batch
from voter_api.models.import_job import ImportJob
from voter_api.models.voter import Voter
from voter_api.schemas.imports import ImportDiffResponse

# asyncpg has a hard limit of 32767 query parameters
_IN_CLAUSE_BATCH = 5000

# Sub-batch size for bulk upsert: ~50 columns * 500 rows = 25,000 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

_DATE_FIELDS = (
    "registration_date",
    "last_modified_date",
    "date_of_last_contact",
    "last_vote_date",
    "voter_created_date",
)

# Columns excluded from the ON CONFLICT UPDATE set.
# voter_registration_number: conflict target key
# first_seen_in_import_id: preserved from original insert
# birth_year: immutable demographic
# voter_created_date: set once when GA SoS creates the record
# id: primary key
# created_at: ORM timestamp, set once
_UPSERT_EXCLUDE_COLUMNS = frozenset(
    {
        "voter_registration_number",
        "first_seen_in_import_id",
        "birth_year",
        "voter_created_date",
        "id",
        "created_at",
    }
)

# Indexes to drop before bulk import and rebuild afterward.
# GIN trigram indexes first (most expensive), then composite B-tree.
_DROPPABLE_INDEXES: list[dict[str, str]] = [
    {
        "name": "ix_voters_first_name_trgm",
        "create": "CREATE INDEX ix_voters_first_name_trgm ON voters USING GIN (first_name gin_trgm_ops)",
    },
    {
        "name": "ix_voters_last_name_trgm",
        "create": "CREATE INDEX ix_voters_last_name_trgm ON voters USING GIN (last_name gin_trgm_ops)",
    },
    {
        "name": "ix_voters_middle_name_trgm",
        "create": "CREATE INDEX ix_voters_middle_name_trgm ON voters USING GIN (middle_name gin_trgm_ops)",
    },
    {
        "name": "ix_voters_name_search",
        "create": "CREATE INDEX ix_voters_name_search ON voters (last_name, first_name)",
    },
    {
        "name": "ix_voters_county_status",
        "create": "CREATE INDEX ix_voters_county_status ON voters (county, status)",
    },
    {
        "name": "ix_voters_county_precinct_combo",
        "create": "CREATE INDEX ix_voters_county_precinct_combo ON voters (county, county_precinct)",
    },
    {
        "name": "ix_voters_status_present",
        "create": "CREATE INDEX ix_voters_status_present ON voters (status, present_in_latest_import)",
    },
    {
        "name": "ix_voters_city_zip",
        "create": "CREATE INDEX ix_voters_city_zip ON voters (residence_city, residence_zipcode)",
    },
]


async def _soft_delete_absent_voters(
    session: AsyncSession,
    county: str | None,
    imported_reg_numbers: set[str],
) -> int:
    """Soft-delete voters from the given county not present in the current import.

    Args:
        session: Database session.
        county: County name to scope the soft-delete (skip if None).
        imported_reg_numbers: Registration numbers seen in this import.

    Returns:
        Number of voters soft-deleted.
    """
    if not county:
        return 0

    existing_result = await session.execute(
        select(Voter.voter_registration_number).where(
            Voter.county == county,
            Voter.present_in_latest_import.is_(True),
        )
    )
    previous_reg_numbers = set(existing_result.scalars().all())
    absent_list = list(previous_reg_numbers - imported_reg_numbers)

    now = datetime.now(UTC)
    for i in range(0, len(absent_list), _IN_CLAUSE_BATCH):
        batch = absent_list[i : i + _IN_CLAUSE_BATCH]
        await session.execute(
            update(Voter)
            .where(Voter.voter_registration_number.in_(batch))
            .values(present_in_latest_import=False, soft_deleted_at=now)
        )

    return len(absent_list)


async def _drop_import_indexes(session: AsyncSession) -> None:
    """Drop non-essential indexes before bulk import.

    Drops GIN trigram and composite B-tree indexes that are expensive
    to maintain during writes. Safe to call even if indexes don't exist.

    Args:
        session: Database session.
    """
    for idx in _DROPPABLE_INDEXES:
        await session.execute(text(f"DROP INDEX IF EXISTS {idx['name']}"))
        logger.debug(f"Dropped index: {idx['name']}")
    await session.commit()
    logger.info(f"Dropped {len(_DROPPABLE_INDEXES)} indexes for bulk import")


async def _rebuild_import_indexes(session: AsyncSession) -> None:
    """Rebuild indexes after bulk import.

    Uses elevated maintenance_work_mem for faster index creation.
    Non-CONCURRENTLY since the import is a dedicated batch process.

    Args:
        session: Database session.
    """
    await session.execute(text("SET maintenance_work_mem = '512MB'"))
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    for idx in _DROPPABLE_INDEXES:
        create_sql = idx["create"].replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS", 1)
        logger.info(f"Rebuilding index: {idx['name']}")
        start = time.monotonic()
        await session.execute(text(create_sql))
        elapsed = time.monotonic() - start
        logger.info(f"Rebuilt index {idx['name']} in {elapsed:.1f}s")

    await session.execute(text("RESET maintenance_work_mem"))
    await session.commit()
    logger.info(f"Rebuilt all {len(_DROPPABLE_INDEXES)} indexes")


async def _disable_autovacuum(session: AsyncSession) -> None:
    """Disable autovacuum on the voters table for bulk import.

    Args:
        session: Database session.
    """
    await session.execute(text("ALTER TABLE voters SET (autovacuum_enabled = false)"))
    await session.commit()
    logger.info("Disabled autovacuum on voters table")


async def _enable_autovacuum_and_vacuum(session: AsyncSession) -> None:
    """Re-enable autovacuum and run VACUUM ANALYZE on the voters table.

    VACUUM cannot run inside a transaction block, so we use the raw
    asyncpg driver connection.

    Args:
        session: Database session.
    """
    await session.execute(text("ALTER TABLE voters SET (autovacuum_enabled = true)"))
    await session.commit()
    logger.info("Re-enabled autovacuum on voters table")

    logger.info("Running VACUUM ANALYZE on voters table...")
    start = time.monotonic()
    engine = get_engine()
    async with engine.connect() as vacuum_conn:
        autocommit_conn = await vacuum_conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit_conn.execute(text("VACUUM ANALYZE voters"))
    elapsed = time.monotonic() - start
    logger.info(f"VACUUM ANALYZE completed in {elapsed:.1f}s")


@asynccontextmanager
async def bulk_import_context(session: AsyncSession) -> AsyncIterator[None]:
    """Context manager for batch voter imports.

    Drops indexes and disables autovacuum once on entry, then rebuilds
    indexes and runs VACUUM ANALYZE once on exit (including on error).

    Use this to wrap multiple calls to ``process_voter_import`` with
    ``skip_optimizations=True`` so the expensive lifecycle operations
    happen exactly once for the entire batch.

    Args:
        session: Database session for lifecycle DDL operations.

    Yields:
        None — caller processes files inside the context.
    """
    try:
        await session.execute(text("SET synchronous_commit = 'off'"))
        await _disable_autovacuum(session)
        await _drop_import_indexes(session)
        logger.info("Bulk import context entered: optimizations applied")
        yield
    finally:
        logger.info("Bulk import context exiting: restoring database settings...")
        try:
            await session.rollback()
            await session.execute(text("SET synchronous_commit = 'on'"))
            await _rebuild_import_indexes(session)
            await _enable_autovacuum_and_vacuum(session)
            logger.info("Bulk import context: database settings restored")
        except Exception:
            logger.exception("Error during bulk import teardown — indexes may need manual rebuild")
            raise


def _coerce_record_types(record: dict) -> None:
    """Parse date fields and birth_year to their DB-native types in place."""
    for field in _DATE_FIELDS:
        val = record.get(field)
        if val:
            try:
                record[field] = parse_date(val).date()
            except (ValueError, TypeError):
                record[field] = None

    birth_year = record.get("birth_year")
    if birth_year is not None:
        try:
            record["birth_year"] = int(birth_year)
        except (ValueError, TypeError):
            record["birth_year"] = None


def _prepare_records_for_db(
    valid_records: list[dict],
    job_id: uuid.UUID,
) -> tuple[list[dict], set[str]]:
    """Prepare validated records for database upsert.

    Strips internal validation fields, parses date/birth_year columns,
    and adds import-tracking columns.

    Args:
        valid_records: Records that passed validation.
        job_id: Current import job ID.

    Returns:
        Tuple of (prepared record dicts, set of registration numbers).
    """
    reg_numbers: set[str] = set()
    prepared: list[dict] = []

    for record in valid_records:
        record.pop("_geocodable", None)
        record.pop("_validation_errors", None)

        reg_num = record.get("voter_registration_number")
        if not reg_num:
            continue

        reg_numbers.add(reg_num)
        _coerce_record_types(record)

        record["present_in_latest_import"] = True
        record["soft_deleted_at"] = None
        record["last_seen_in_import_id"] = job_id
        record["first_seen_in_import_id"] = job_id

        prepared.append(record)

    return prepared, reg_numbers


async def _upsert_voter_batch(
    session: AsyncSession,
    records: list[dict],
) -> tuple[int, int]:
    """Bulk upsert voter records using PostgreSQL INSERT ... ON CONFLICT.

    Uses the unique index on ``voter_registration_number`` as the conflict
    target. On conflict, all data columns are updated except
    ``first_seen_in_import_id`` (preserved from the original insert).

    Splits records into sub-batches of ``_UPSERT_SUB_BATCH`` to stay
    within asyncpg's 32,767 query-parameter limit.

    Args:
        session: Database session.
        records: Prepared record dicts (from ``_prepare_records_for_db``).

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not records:
        return 0, 0

    total_inserted = 0
    total_updated = 0

    # Columns to update on conflict — everything except immutable columns
    # (conflict key, PK, timestamps, demographics that don't change).
    update_columns = sorted(set(records[0].keys()) - _UPSERT_EXCLUDE_COLUMNS)

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Voter).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["voter_registration_number"],
            set_={col: stmt.excluded[col] for col in update_columns},
        )
        # xmax = 0 identifies genuinely new rows (not updated via ON CONFLICT)
        stmt = stmt.returning(  # type: ignore[assignment]
            Voter.voter_registration_number,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


async def create_import_job(
    session: AsyncSession,
    *,
    file_name: str,
    file_type: str = "voter_csv",
    triggered_by: uuid.UUID | None = None,
) -> ImportJob:
    """Create a new import job record.

    Args:
        session: Database session.
        file_name: Original filename.
        file_type: Type of import (voter_csv, shapefile, geojson).
        triggered_by: User ID who triggered the import.

    Returns:
        The created ImportJob.
    """
    job = ImportJob(
        file_name=file_name,
        file_type=file_type,
        status="pending",
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _process_chunk(
    session: AsyncSession,
    job: ImportJob,
    chunk: pd.DataFrame,
    chunk_idx: int,
    errors: list[dict],
    imported_reg_numbers: set[str],
) -> tuple[int, int, int, str | None]:
    """Validate and upsert a single CSV chunk.

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        chunk: DataFrame chunk from the CSV parser.
        chunk_idx: Zero-based chunk index (for logging).
        errors: Mutable list to append validation errors to.
        imported_reg_numbers: Mutable set to accumulate registration numbers.

    Returns:
        Tuple of (total_in_chunk, chunk_inserted, chunk_updated, detected_county).
    """
    records = [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in chunk.to_dict("records")]

    # Detect county for scoped soft-delete
    detected_county = records[0].get("county") if records else None

    valid_records, failed_records = validate_batch(records)

    logger.info(
        f"Chunk {chunk_idx + 1}: {len(records)} records ({len(valid_records)} valid, {len(failed_records)} failed)"
    )

    errors.extend(
        {
            "voter_registration_number": fr.get("voter_registration_number", "unknown"),
            "errors": fr.get("_validation_errors", []),
        }
        for fr in failed_records
    )

    # Prepare and bulk-upsert valid records
    db_records, chunk_reg_numbers = _prepare_records_for_db(valid_records, job.id)
    imported_reg_numbers.update(chunk_reg_numbers)

    chunk_inserted, chunk_updated = await _upsert_voter_batch(session, db_records)

    return len(records), chunk_inserted, chunk_updated, detected_county


async def process_voter_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
    batch_size: int = 5000,
    *,
    skip_optimizations: bool = False,
    max_records: int | None = None,
) -> ImportJob:
    """Process a voter CSV file import with bulk optimizations.

    Reads the file in chunks, validates records, upserts voters,
    soft-deletes absent voters, and generates a diff report.

    Performance optimizations applied during import (unless skipped):
    - Drops non-essential indexes, rebuilds after
    - Sets synchronous_commit = off for the session
    - Disables autovacuum, runs VACUUM ANALYZE after

    When ``skip_optimizations=True``, the caller is responsible for
    managing the DB optimization lifecycle (e.g., via ``bulk_import_context``).

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        file_path: Path to the CSV file.
        batch_size: Records per processing batch.
        skip_optimizations: If True, skip index drop/rebuild, autovacuum,
            and synchronous_commit changes. Use when calling within
            ``bulk_import_context``.
        max_records: If set, stop importing after this many records.
            Soft-delete is skipped for partial imports.

    Returns:
        The updated ImportJob with final counts.
    """
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()

    total = 0
    inserted = 0
    updated_count = 0
    errors: list[dict] = []
    imported_reg_numbers: set[str] = set()
    import_county: str | None = None

    try:
        import_start = time.monotonic()
        if not skip_optimizations:
            # --- Bulk import optimizations ---
            logger.info("Applying bulk import optimizations...")
            await session.execute(text("SET synchronous_commit = 'off'"))
            await _disable_autovacuum(session)
            await _drop_import_indexes(session)
            logger.info("Bulk import optimizations applied")

        chunk_offset = job.last_processed_offset or 0
        for chunk_idx, chunk in enumerate(parse_csv_chunks(file_path, batch_size)):
            if chunk_idx < chunk_offset:
                continue

            chunk_start = time.monotonic()

            chunk_total, chunk_inserted, chunk_updated, detected_county = await _process_chunk(
                session,
                job,
                chunk,
                chunk_idx,
                errors,
                imported_reg_numbers,
            )
            total += chunk_total
            inserted += chunk_inserted
            updated_count += chunk_updated

            if import_county is None and detected_county:
                import_county = detected_county
                logger.info(f"Detected county: {import_county}")

            # Update checkpoint and commit batch atomically
            job.last_processed_offset = chunk_idx + 1
            await session.commit()

            chunk_elapsed = time.monotonic() - chunk_start
            logger.info(
                f"Chunk {chunk_idx + 1} committed: "
                f"{chunk_inserted} inserted, {chunk_updated} updated "
                f"({chunk_elapsed:.1f}s) | running total: {total} records"
            )

            if max_records is not None and total >= max_records:
                logger.info(f"Reached max_records limit ({max_records}), stopping import")
                break

        # Soft-delete absent voters scoped to the imported county
        # Skip when max_records is set — partial imports should not mark
        # absent voters as deleted.
        soft_deleted = 0
        if max_records is None:
            logger.info(f"Checking for absent voters in county {import_county}")
            soft_deleted = await _soft_delete_absent_voters(session, import_county, imported_reg_numbers)
        else:
            logger.info("Skipping soft-delete (partial import with max_records limit)")

        failed = len(errors)
        succeeded = inserted + updated_count

        # Update job status and commit everything atomically
        job.status = "completed"
        job.total_records = total
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.records_inserted = inserted
        job.records_updated = updated_count
        job.records_soft_deleted = soft_deleted
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        import_elapsed = time.monotonic() - import_start
        logger.info(
            f"Import data phase completed in {import_elapsed:.1f}s: "
            f"{total} total, {succeeded} succeeded, {failed} failed, "
            f"{inserted} inserted, {updated_count} updated, {soft_deleted} soft-deleted"
        )

    except Exception:
        await session.rollback()
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    finally:
        if not skip_optimizations:
            # --- Restore database settings (always runs, even on failure) ---
            logger.info("Restoring database settings...")
            try:
                # Roll back any pending failed transaction before teardown
                await session.rollback()
                await session.execute(text("SET synchronous_commit = 'on'"))
                await _rebuild_import_indexes(session)
                await _enable_autovacuum_and_vacuum(session)
                logger.info("Database settings restored")
            except Exception:
                logger.exception("Error during optimization teardown — indexes may need manual rebuild")

    return job


async def get_import_job(session: AsyncSession, job_id: uuid.UUID) -> ImportJob | None:
    """Get an import job by ID.

    Args:
        session: Database session.
        job_id: The import job ID.

    Returns:
        The ImportJob or None if not found.
    """
    result = await session.execute(select(ImportJob).where(ImportJob.id == job_id))
    return result.scalar_one_or_none()


async def list_import_jobs(
    session: AsyncSession,
    *,
    file_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ImportJob], int]:
    """List import jobs with optional filters.

    Args:
        session: Database session.
        file_type: Filter by file type.
        status: Filter by status.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (jobs, total count).
    """
    from sqlalchemy import func

    query = select(ImportJob)
    count_query = select(func.count(ImportJob.id))

    if file_type:
        query = query.where(ImportJob.file_type == file_type)
        count_query = count_query.where(ImportJob.file_type == file_type)
    if status:
        query = query.where(ImportJob.status == status)
        count_query = count_query.where(ImportJob.status == status)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(ImportJob.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    jobs = list(result.scalars().all())

    return jobs, total


async def get_import_diff(session: AsyncSession, job_id: uuid.UUID) -> ImportDiffResponse | None:
    """Get the diff report for an import job.

    This is a simplified implementation that reconstructs the diff
    from the job's import data.

    Args:
        session: Database session.
        job_id: The import job ID.

    Returns:
        ImportDiffResponse or None if job not found.
    """
    job = await get_import_job(session, job_id)
    if job is None:
        return None

    # Get voters first seen in this import (added)
    added_result = await session.execute(
        select(Voter.voter_registration_number).where(Voter.first_seen_in_import_id == job_id)
    )
    added = list(added_result.scalars().all())

    # Get voters soft-deleted during this import period
    removed_result = await session.execute(
        select(Voter.voter_registration_number).where(
            Voter.present_in_latest_import.is_(False),
            Voter.last_seen_in_import_id != job_id,
        )
    )
    removed = list(removed_result.scalars().all())

    # Get voters updated in this import (last_seen but not first_seen)
    updated_result = await session.execute(
        select(Voter.voter_registration_number).where(
            Voter.last_seen_in_import_id == job_id,
            Voter.first_seen_in_import_id != job_id,
        )
    )
    updated = list(updated_result.scalars().all())

    return ImportDiffResponse(job_id=job_id, added=added, removed=removed, updated=updated)
