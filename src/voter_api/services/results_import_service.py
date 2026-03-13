"""Election results import service — orchestrates JSON file import."""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.district_parser.parser import parse_election_district
from voter_api.lib.election_name_normalizer import normalize_election_name
from voter_api.lib.results_importer import (
    BallotItemContext,
    iter_ballot_items,
    load_results_file,
    validate_results_file,
)
from voter_api.models.candidate import Candidate
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob
from voter_api.services.election_resolution_service import find_or_create_election_event
from voter_api.services.election_service import persist_ingestion_result

_CANDIDATE_UPSERT_BATCH = 500


async def create_results_import_job(
    session: AsyncSession,
    file_name: str,
    triggered_by: uuid.UUID | None = None,
) -> ImportJob:
    """Create a new import job for election results import."""
    job = ImportJob(
        file_name=file_name,
        file_type="election_results",
        status="pending",
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _match_election(
    session: AsyncSession,
    ctx: BallotItemContext,
    election_cache: dict[tuple[str, date], uuid.UUID],
) -> uuid.UUID:
    """Match a ballot item to an existing election or auto-create one.

    Uses a 3-tier matching strategy:

    Tier 1: Match by ballot_item_id + election_date (exact).
    Tier 2: Parse ballot_item_name via parse_election_district() and match on
            (district_type, district_identifier, district_party, election_date).
            Backfill ballot_item_id on match.
    Tier 3: Auto-create election with name "{electionName} - {ballotItem.name}",
            source="sos_feed", status="finalized".

    Special: For recount files (electionName contains "Recount"), if Tier 1
    returns multiple rows, prefer the one whose name also contains "Recount".
    """
    cache_key = (ctx.ballot_item_id, ctx.election_date)
    if cache_key in election_cache:
        return election_cache[cache_key]

    is_recount = "recount" in ctx.election_event_name.lower()

    # --- Tier 1: ballot_item_id + election_date ---
    stmt = select(Election).where(
        Election.ballot_item_id == ctx.ballot_item_id,
        Election.election_date == ctx.election_date,
        Election.deleted_at.is_(None),
    )
    result = await session.execute(stmt)
    matches = list(result.scalars().all())

    if matches:
        if len(matches) == 1:
            election_cache[cache_key] = matches[0].id
            return matches[0].id
        # Multiple matches — for recounts, prefer recount election
        if is_recount:
            recount_matches = [e for e in matches if "recount" in (e.name or "").lower()]
            if recount_matches:
                election_cache[cache_key] = recount_matches[0].id
                return recount_matches[0].id
        # Fall through to first match
        election_cache[cache_key] = matches[0].id
        return matches[0].id

    # --- Tier 2: district matching ---
    parsed = parse_election_district(ctx.ballot_item_name)
    if parsed.district_type and parsed.district_identifier:
        tier2_stmt = select(Election).where(
            Election.district_type == parsed.district_type,
            Election.district_identifier == parsed.district_identifier,
            Election.election_date == ctx.election_date,
            Election.deleted_at.is_(None),
        )
        if parsed.party:
            tier2_stmt = tier2_stmt.where(Election.district_party == parsed.party)
        # Narrow by geography when available to prevent county/municipality-scoped
        # contests that share the same district_type+identifier on the same date
        # from colliding (e.g. two different county commission district 5s).
        if parsed.county:
            tier2_stmt = tier2_stmt.where(Election.eligible_county == parsed.county.upper())

        result = await session.execute(tier2_stmt)
        tier2_match = result.scalar_one_or_none()
        if tier2_match:
            # Backfill ballot_item_id for future lookups
            tier2_match.ballot_item_id = ctx.ballot_item_id
            await session.flush()
            election_cache[cache_key] = tier2_match.id
            logger.info(
                "Tier 2 match for '{}' -> election {} (backfilled ballot_item_id={})",
                ctx.ballot_item_name,
                tier2_match.id,
                ctx.ballot_item_id,
            )
            return tier2_match.id

    # --- Tier 3: auto-create ---
    election_name = f"{ctx.election_event_name} - {ctx.ballot_item_name}"
    # Strip Spanish translation suffix if present
    if "/" in ctx.ballot_item_name:
        clean_name = ctx.ballot_item_name.split("/", 1)[0].strip()
        election_name = f"{ctx.election_event_name} - {clean_name}"

    # Preserve original name and normalize for storage
    source_name = election_name
    normalized_name = normalize_election_name(election_name)

    # Find or create the parent ElectionEvent for this election day
    event_id = await find_or_create_election_event(
        session,
        event_date=ctx.election_date,
        event_type=ctx.election_type,
        event_name=ctx.election_event_name,
    )

    new_id = uuid.uuid4()
    stmt_insert = (
        pg_insert(Election)
        .values(
            id=new_id,
            name=normalized_name,
            source_name=source_name,
            election_date=ctx.election_date,
            election_type=ctx.election_type,
            district=ctx.ballot_item_name,
            source="sos_feed",
            creation_method="manual",
            status="finalized",
            ballot_item_id=ctx.ballot_item_id,
            district_type=parsed.district_type if parsed.district_type else None,
            district_identifier=(parsed.district_identifier if parsed.district_identifier else None),
            district_party=parsed.party if parsed.party else None,
            election_event_id=event_id,
        )
        .on_conflict_do_nothing()
        .returning(Election.__table__.c.id)
    )

    result = await session.execute(stmt_insert)
    inserted_row = result.scalar_one_or_none()
    if inserted_row is None:
        # Election already exists with this name+date, fetch it
        existing = await session.execute(
            select(Election.id).where(
                Election.name == normalized_name,
                Election.election_date == ctx.election_date,
                Election.deleted_at.is_(None),
            )
        )
        existing_id = existing.scalar_one_or_none()
        if existing_id:
            election_cache[cache_key] = existing_id
            return existing_id

    await session.flush()
    election_cache[cache_key] = new_id
    logger.info("Tier 3: created election '{}' -> {}", normalized_name, new_id)
    return new_id


async def _upsert_candidates(
    session: AsyncSession,
    election_id: uuid.UUID,
    ctx: BallotItemContext,
    job_id: uuid.UUID,
) -> tuple[int, int]:
    """Upsert candidates from ballot options for a single election.

    Uses INSERT ... ON CONFLICT (election_id, full_name) DO UPDATE with
    conservative update rules:
    - Always update: sos_ballot_option_id, ballot_order, party (if NULL)
    - Set if True: is_incumbent (never flip to False)
    - Never overwrite: bio, photo_url, filing_status, contest_name, etc.

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not ctx.candidates:
        return 0, 0

    records = []
    for c in ctx.candidates:
        records.append(
            {
                "id": uuid.uuid4(),
                "election_id": election_id,
                "full_name": c.full_name,
                "party": c.party,
                "ballot_order": c.ballot_order,
                "is_incumbent": c.is_incumbent,
                "sos_ballot_option_id": c.sos_ballot_option_id,
                "import_job_id": job_id,
            }
        )

    total_inserted = 0
    total_updated = 0

    for i in range(0, len(records), _CANDIDATE_UPSERT_BATCH):
        batch = records[i : i + _CANDIDATE_UPSERT_BATCH]
        stmt = pg_insert(Candidate).values(batch)

        # Conservative update: only update fields that should be overwritten
        update_set = {
            "sos_ballot_option_id": stmt.excluded.sos_ballot_option_id,
            "ballot_order": stmt.excluded.ballot_order,
            "import_job_id": stmt.excluded.import_job_id,
        }

        stmt = stmt.on_conflict_do_update(
            constraint="uq_candidate_election_name",
            set_=update_set,
        )
        stmt = stmt.returning(  # type: ignore[assignment]
            Candidate.__table__.c.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()
        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    # Post-upsert: conditionally update party and is_incumbent
    # Party: only set if currently NULL
    # is_incumbent: only set to True, never flip to False
    for c in ctx.candidates:
        if c.party or c.is_incumbent:
            existing = await session.execute(
                select(Candidate).where(
                    Candidate.election_id == election_id,
                    Candidate.full_name == c.full_name,
                )
            )
            candidate = existing.scalar_one_or_none()
            if candidate:
                if c.party and not candidate.party:
                    candidate.party = c.party
                if c.is_incumbent and not candidate.is_incumbent:
                    candidate.is_incumbent = True

    return total_inserted, total_updated


async def process_results_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
) -> ImportJob:
    """Process a single election results JSON file.

    Loads the file, validates it, matches/creates elections, upserts
    candidates, and persists results.

    Args:
        session: Database session.
        job: The ImportJob tracking this import.
        file_path: Path to the JSON file.

    Returns:
        Updated ImportJob with final counts.
    """
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()

    errors: list[dict] = []
    elections_processed = 0
    candidates_inserted = 0
    candidates_updated = 0
    results_persisted = 0
    election_cache: dict[tuple[str, date], uuid.UUID] = {}

    try:
        # Load and validate
        feed = load_results_file(file_path)
        validation_errors = validate_results_file(feed)
        if validation_errors:
            job.status = "failed"
            job.error_log = [{"error": e} for e in validation_errors]
            job.completed_at = datetime.now(UTC)
            await session.commit()
            return job

        # Iterate ballot items
        contexts = iter_ballot_items(feed)
        job.total_records = len(contexts)
        await session.commit()

        for ctx in contexts:
            try:
                # Use a savepoint so that a single ballot-item failure can be
                # rolled back without poisoning the session for subsequent items.
                async with session.begin_nested():
                    # Match or create election
                    election_id = await _match_election(session, ctx, election_cache)
                    elections_processed += 1

                    # Upsert candidates
                    c_ins, c_upd = await _upsert_candidates(session, election_id, ctx, job.id)
                    candidates_inserted += c_ins
                    candidates_updated += c_upd

                    # Persist results (statewide + county)
                    counties_updated = await persist_ingestion_result(session, election_id, ctx.ingestion)
                    results_persisted += 1 + counties_updated  # 1 for statewide + counties

            except Exception as e:
                logger.warning(
                    "Error processing ballot item '{}': {}",
                    ctx.ballot_item_name,
                    e,
                )
                errors.append(
                    {
                        "ballot_item": ctx.ballot_item_name,
                        "ballot_item_id": ctx.ballot_item_id,
                        "error": str(e),
                    }
                )

        # Finalize
        job.status = "completed"
        job.records_succeeded = elections_processed
        job.records_failed = len(errors)
        job.records_inserted = candidates_inserted
        job.records_updated = candidates_updated
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            "Results import completed for '{}': {} ballot items, {} candidates ({} new, {} updated), {} result rows",
            file_path.name,
            elections_processed,
            candidates_inserted + candidates_updated,
            candidates_inserted,
            candidates_updated,
            results_persisted,
        )

    except Exception:
        await session.rollback()
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    return job
