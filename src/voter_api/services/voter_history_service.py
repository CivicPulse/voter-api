"""Voter history service — import, query, and aggregate participation data."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.voter_history import (
    generate_election_name,
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
)

# asyncpg has a hard limit of 32767 query parameters
_IN_CLAUSE_BATCH = 5000


async def process_voter_history_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
    batch_size: int = 1000,
) -> ImportJob:
    """Process a voter history CSV file import.

    Reads the file in chunks, validates records, upserts voter history,
    tracks unmatched voters and duplicates, and handles re-import replacement.

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
    succeeded = 0
    failed = 0
    skipped = 0
    unmatched = 0
    elections_created = 0
    errors: list[dict] = []
    seen_keys: set[tuple[str, str, str]] = set()

    try:
        for chunk_idx, records in enumerate(parse_voter_history_chunks(file_path, batch_size)):
            total += len(records)

            valid_records: list[dict] = []
            for record in records:
                parse_error = record.pop("_parse_error", None)
                if parse_error:
                    failed += 1
                    errors.append(
                        {
                            "voter_registration_number": record.get("voter_registration_number", "unknown"),
                            "error": parse_error,
                        }
                    )
                    continue

                # Duplicate detection within file
                key = (
                    record["voter_registration_number"],
                    str(record["election_date"]),
                    record["election_type"],
                )
                if key in seen_keys:
                    skipped += 1
                    continue
                seen_keys.add(key)

                valid_records.append(record)

            # Auto-create elections for this batch
            batch_created = await _auto_create_elections(session, valid_records)
            elections_created += batch_created

            # Detect unmatched voters in this batch
            batch_unmatched = await _count_unmatched_voters(session, valid_records)
            unmatched += batch_unmatched

            # Batch upsert voter history records
            if valid_records:
                await _upsert_voter_history_batch(session, valid_records, job.id)
                succeeded += len(valid_records)

            # Flush and update checkpoint
            await session.flush()
            job.last_processed_offset = chunk_idx + 1
            await session.commit()

        # Re-import replacement: clean up records from previous imports of same file
        await _replace_previous_import(session, job)

        # Finalize job
        job.status = "completed"
        job.total_records = total
        job.records_succeeded = succeeded
        job.records_failed = failed
        job.records_inserted = succeeded
        job.records_skipped = skipped
        job.records_unmatched = unmatched
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            f"Voter history import completed: {total} total, "
            f"{succeeded} succeeded, {failed} failed, {skipped} skipped, "
            f"{unmatched} unmatched, {elections_created} elections created"
        )

    except Exception:
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

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
        for r in records
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


async def _auto_create_elections(
    session: AsyncSession,
    records: list[dict],
) -> int:
    """Auto-create election records for date+type combos not yet in the DB.

    Args:
        session: Database session.
        records: List of valid record dicts.

    Returns:
        Number of elections created.
    """
    # Extract unique (date, raw_type) combos
    combos: dict[tuple[date, str], str] = {}
    for r in records:
        ed = r["election_date"]
        raw_type = r["election_type"]
        if (ed, raw_type) not in combos:
            combos[(ed, raw_type)] = r["normalized_election_type"]

    if not combos:
        return 0

    created = 0
    for (election_date, raw_type), normalized_type in combos.items():
        # Check if election already exists
        result = await session.execute(
            select(Election.id).where(
                Election.election_date == election_date,
                Election.election_type == normalized_type,
            )
        )
        if result.scalar_one_or_none() is not None:
            continue

        # Auto-create
        name = generate_election_name(raw_type, election_date)
        election = Election(
            name=name,
            election_date=election_date,
            election_type=normalized_type,
            creation_method="voter_history",
            status="finalized",
            district="Statewide",
            data_source_url="n/a",
        )
        session.add(election)
        created += 1
        logger.info(f"Auto-created election: {name} (type={normalized_type}, date={election_date})")

    if created:
        await session.flush()

    return created


async def _count_unmatched_voters(
    session: AsyncSession,
    records: list[dict],
) -> int:
    """Count records whose voter registration numbers are not in the voters table.

    Args:
        session: Database session.
        records: List of valid record dicts.

    Returns:
        Count of unmatched records.
    """
    reg_numbers = list({r["voter_registration_number"] for r in records})
    if not reg_numbers:
        return 0

    matched: set[str] = set()
    for i in range(0, len(reg_numbers), _IN_CLAUSE_BATCH):
        batch = reg_numbers[i : i + _IN_CLAUSE_BATCH]
        result = await session.execute(
            select(Voter.voter_registration_number).where(Voter.voter_registration_number.in_(batch))
        )
        matched.update(result.scalars().all())

    return sum(1 for r in records if r["voter_registration_number"] not in matched)


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

    query = select(VoterHistory).where(
        VoterHistory.election_date == election.election_date,
        VoterHistory.normalized_election_type == election.election_type,
    )
    count_query = select(func.count(VoterHistory.id)).where(
        VoterHistory.election_date == election.election_date,
        VoterHistory.normalized_election_type == election.election_type,
    )

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

    base_where = [
        VoterHistory.election_date == election.election_date,
        VoterHistory.normalized_election_type == election.election_type,
    ]

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

    return ParticipationStatsResponse(
        election_id=election_id,
        total_participants=total_participants,
        by_county=by_county,
        by_ballot_style=by_ballot_style,
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
