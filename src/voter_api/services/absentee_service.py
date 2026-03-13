"""Absentee ballot application service — import, query, and stats."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.utils import _mask_vrn
from voter_api.lib.absentee import parse_absentee_csv_chunks
from voter_api.models.absentee_ballot import AbsenteeBallotApplication
from voter_api.models.import_job import ImportJob

# Sub-batch size: 38 columns * 400 rows = 15,200 params (under 32,767 asyncpg limit)
_UPSERT_SUB_BATCH = 400

# Columns to update on conflict (everything except the unique key columns and id)
_UPDATE_COLUMNS = [
    "county",
    "last_name",
    "first_name",
    "middle_name",
    "suffix",
    "street_number",
    "street_name",
    "apt_unit",
    "city",
    "state",
    "zip_code",
    "mailing_street_number",
    "mailing_street_name",
    "mailing_apt_unit",
    "mailing_city",
    "mailing_state",
    "mailing_zip_code",
    "application_status",
    "ballot_status",
    "status_reason",
    "ballot_issued_date",
    "ballot_return_date",
    "ballot_assisted",
    "challenged_provisional",
    "id_required",
    "municipal_precinct",
    "county_precinct",
    "congressional_district",
    "state_senate_district",
    "state_house_district",
    "judicial_district",
    "combo",
    "vote_center_id",
    "ballot_id",
    "party",
    "import_job_id",
]


async def create_absentee_import_job(
    session: AsyncSession,
    file_name: str,
    triggered_by: uuid.UUID | None = None,
) -> ImportJob:
    """Create a new import job for absentee ballot application import.

    Args:
        session: Database session.
        file_name: Original filename.
        triggered_by: User ID who triggered the import.

    Returns:
        The created ImportJob.
    """
    job = ImportJob(
        file_name=file_name,
        file_type="absentee",
        status="pending",
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _upsert_absentee_batch(
    session: AsyncSession,
    records: list[dict],
) -> tuple[int, int]:
    """Bulk upsert absentee ballot records using PostgreSQL INSERT ... ON CONFLICT.

    Uses the unique constraint on ``(voter_registration_number, application_date,
    ballot_style)`` as the conflict target.

    Args:
        session: Database session.
        records: Prepared absentee ballot record dicts.

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not records:
        return 0, 0

    total_inserted = 0
    total_updated = 0

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(AbsenteeBallotApplication).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                AbsenteeBallotApplication.__table__.c.voter_registration_number,
                AbsenteeBallotApplication.__table__.c.application_date,
                text("COALESCE(ballot_style, '')"),
            ],
            set_={col: stmt.excluded[col] for col in _UPDATE_COLUMNS},
        )
        # xmax = 0 identifies genuinely new rows (not updated via ON CONFLICT)
        stmt = stmt.returning(  # type: ignore[assignment]
            AbsenteeBallotApplication.__table__.c.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


async def process_absentee_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
    batch_size: int = 400,
) -> ImportJob:
    """Process an absentee ballot application CSV file import with bulk upsert.

    Reads the CSV file in batches using the absentee parser, validates records,
    and upserts them into the database.

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        file_path: Path to the absentee ballot CSV file.
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

    try:
        chunk_offset = job.last_processed_offset or 0
        for chunk_idx, records in enumerate(parse_absentee_csv_chunks(file_path, batch_size)):
            if chunk_idx < chunk_offset:
                continue

            chunk_total = len(records)
            total += chunk_total

            # Separate valid and invalid records
            valid_records: list[dict] = []

            for record in records:
                parse_error = record.pop("_parse_error", None)
                if parse_error:
                    errors.append(
                        {
                            "voter_registration_number": _mask_vrn(record.get("voter_registration_number", "unknown")),
                            "error": parse_error,
                        }
                    )
                    continue

                # Build DB record
                db_record = {
                    "id": uuid.uuid4(),
                    "import_job_id": job.id,
                }
                # Copy all model fields from parsed record
                for key, value in record.items():
                    if not key.startswith("_"):
                        db_record[key] = value

                valid_records.append(db_record)

            # Upsert batch
            chunk_inserted, chunk_updated = await _upsert_absentee_batch(session, valid_records)
            inserted += chunk_inserted
            updated_count += chunk_updated

            # Update checkpoint and commit batch
            job.last_processed_offset = chunk_idx + 1
            await session.commit()

            logger.info(
                f"Chunk {chunk_idx + 1}: {chunk_total} records "
                f"({chunk_inserted} inserted, {chunk_updated} updated) | "
                f"running total: {total} records"
            )

        # Finalize job
        failed = len(errors)
        succeeded = inserted + updated_count

        job.status = "completed"
        job.total_records = total
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.records_inserted = inserted
        job.records_updated = updated_count
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            f"Absentee import completed: {total} total, {succeeded} succeeded, "
            f"{failed} failed, {inserted} inserted, {updated_count} updated"
        )

    except Exception:
        await session.rollback()
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    return job


async def query_absentee_ballots(
    session: AsyncSession,
    county: str | None = None,
    voter_registration_number: str | None = None,
    application_status: str | None = None,
    ballot_status: str | None = None,
    party: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[AbsenteeBallotApplication], int]:
    """Query absentee ballot applications with optional filters and pagination.

    Args:
        session: Database session.
        county: Filter by county name.
        voter_registration_number: Filter by voter registration number.
        application_status: Filter by application status.
        ballot_status: Filter by ballot status.
        party: Filter by party.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (list of AbsenteeBallotApplication records, total count).
    """
    query = select(AbsenteeBallotApplication)
    count_query = select(func.count(AbsenteeBallotApplication.id))

    if county:
        query = query.where(AbsenteeBallotApplication.county == county)
        count_query = count_query.where(AbsenteeBallotApplication.county == county)
    if voter_registration_number:
        query = query.where(AbsenteeBallotApplication.voter_registration_number == voter_registration_number)
        count_query = count_query.where(
            AbsenteeBallotApplication.voter_registration_number == voter_registration_number
        )
    if application_status:
        query = query.where(AbsenteeBallotApplication.application_status == application_status)
        count_query = count_query.where(AbsenteeBallotApplication.application_status == application_status)
    if ballot_status:
        query = query.where(AbsenteeBallotApplication.ballot_status == ballot_status)
        count_query = count_query.where(AbsenteeBallotApplication.ballot_status == ballot_status)
    if party:
        query = query.where(AbsenteeBallotApplication.party == party)
        count_query = count_query.where(AbsenteeBallotApplication.party == party)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar_one()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(AbsenteeBallotApplication.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    records = list(result.scalars().all())

    return records, total


async def get_absentee_ballot(
    session: AsyncSession,
    ballot_id: uuid.UUID,
) -> AbsenteeBallotApplication | None:
    """Get a single absentee ballot application by ID.

    Args:
        session: Database session.
        ballot_id: The absentee ballot application UUID.

    Returns:
        The AbsenteeBallotApplication or None if not found.
    """
    result = await session.execute(select(AbsenteeBallotApplication).where(AbsenteeBallotApplication.id == ballot_id))
    return result.scalar_one_or_none()


async def get_absentee_stats(
    session: AsyncSession,
    county: str | None = None,
) -> dict:
    """Get aggregate statistics for absentee ballot applications.

    Args:
        session: Database session.
        county: Optional county filter.

    Returns:
        Dict with total_applications, by_county, by_status, by_party.
    """
    base_filter = []
    if county:
        base_filter.append(AbsenteeBallotApplication.county == county)

    # Total count
    total_query = select(func.count(AbsenteeBallotApplication.id))
    if base_filter:
        total_query = total_query.where(*base_filter)
    total_result = await session.execute(total_query)
    total = total_result.scalar_one()

    # By county
    county_query = select(
        AbsenteeBallotApplication.county,
        func.count(AbsenteeBallotApplication.id),
    ).group_by(AbsenteeBallotApplication.county)
    if base_filter:
        county_query = county_query.where(*base_filter)
    county_result = await session.execute(county_query)
    by_county = {row[0]: row[1] for row in county_result.all() if row[0] is not None}

    # By application status
    status_query = select(
        AbsenteeBallotApplication.application_status,
        func.count(AbsenteeBallotApplication.id),
    ).group_by(AbsenteeBallotApplication.application_status)
    if base_filter:
        status_query = status_query.where(*base_filter)
    status_result = await session.execute(status_query)
    by_status = {row[0]: row[1] for row in status_result.all() if row[0] is not None}

    # By party
    party_query = select(
        AbsenteeBallotApplication.party,
        func.count(AbsenteeBallotApplication.id),
    ).group_by(AbsenteeBallotApplication.party)
    if base_filter:
        party_query = party_query.where(*base_filter)
    party_result = await session.execute(party_query)
    by_party = {row[0]: row[1] for row in party_result.all() if row[0] is not None}

    return {
        "total_applications": total,
        "by_county": by_county,
        "by_status": by_status,
        "by_party": by_party,
    }
