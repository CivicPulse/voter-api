"""Import service — orchestrates voter file import with upsert, soft-delete, and diff tracking."""

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dateutil.parser import parse as parse_date
from loguru import logger
from sqlalchemy import literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

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
    if birth_year:
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

    # Columns to update on conflict — everything except the conflict key
    # and first_seen_in_import_id (which should only be set on initial insert).
    update_columns = sorted(set(records[0].keys()) - {"voter_registration_number", "first_seen_in_import_id"})

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Voter).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["voter_registration_number"],
            set_={col: stmt.excluded[col] for col in update_columns},
        )
        # xmax = 0 identifies genuinely new rows (not updated via ON CONFLICT)
        stmt = stmt.returning(
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
    batch_size: int = 1000,
) -> ImportJob:
    """Process a voter CSV file import.

    Reads the file in chunks, validates records, upserts voters,
    soft-deletes absent voters, and generates a diff report.

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        file_path: Path to the CSV file.
        batch_size: Records per processing batch.

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

        # Soft-delete absent voters scoped to the imported county
        logger.info(f"Checking for absent voters in county {import_county}")
        soft_deleted = await _soft_delete_absent_voters(session, import_county, imported_reg_numbers)

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

        logger.info(
            f"Import completed: {total} total, {succeeded} succeeded, "
            f"{failed} failed, {inserted} inserted, {updated_count} updated, "
            f"{soft_deleted} soft-deleted"
        )

    except Exception:
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

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
