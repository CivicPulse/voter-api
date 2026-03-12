"""Candidate import service — orchestrates candidate JSONL import with upsert and election resolution."""

import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.candidate_importer import parse_candidate_import_jsonl
from voter_api.lib.election_name_normalizer import normalize_election_name
from voter_api.models.candidate import Candidate, CandidateLink
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob

# Sub-batch size for candidate upsert: ~15 columns * 500 rows = 7,500 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

# Pattern matching trailing party markers like (R), (D), (NP), (I)
_PARTY_MARKER_RE = re.compile(r"\s*\([RDNPI]+\)\s*$")


def _normalize_election_name(name: str) -> str:
    """Normalize an election name for deduplication lookups.

    Strips trailing party markers such as ``(R)``, ``(D)``, ``(NP)``,
    ``(I)``, collapses whitespace, and lowercases the result.

    Args:
        name: Raw election/contest name.

    Returns:
        Normalized lowercase name suitable for cache key comparison.
    """
    stripped = _PARTY_MARKER_RE.sub("", name)
    collapsed = re.sub(r"\s+", " ", stripped).strip()
    return collapsed.lower()


async def create_candidate_import_job(
    session: AsyncSession,
    file_name: str,
    triggered_by: uuid.UUID | None = None,
) -> ImportJob:
    """Create a new import job for candidate import.

    Args:
        session: Database session.
        file_name: Original filename.
        triggered_by: User ID who triggered the import.

    Returns:
        The created ImportJob.
    """
    job = ImportJob(
        file_name=file_name,
        file_type="candidate_import",
        status="pending",
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def _resolve_election(
    session: AsyncSession,
    election_name: str,
    election_date: date,
    election_type: str | None,
    cache: dict[tuple[str, date], uuid.UUID],
    county: str | None = None,
    municipality: str | None = None,
) -> uuid.UUID:
    """Resolve or create an election for a candidate record.

    Looks up an existing election by normalized name and date. If not found,
    creates one directly via pg_insert using the original (non-normalized)
    name. Caches lookups by normalized name to prevent duplicates caused by
    trailing party markers like ``(R)`` or ``(D)``.

    When county or municipality is provided, backfills eligible_county /
    eligible_municipality on existing elections that lack these fields.

    Args:
        session: Database session.
        election_name: Election/contest name (original, non-normalized).
        election_date: Election date.
        election_type: Election type (e.g. primary, general).
        cache: Mutable lookup cache mapping (normalized_name, date) to election_id.
        county: County name from the candidate CSV (for geographic scoping).
        municipality: Municipality name from the candidate CSV.

    Returns:
        The election UUID.
    """
    original_name = re.sub(r"\s+", " ", election_name).strip()
    normalized = _normalize_election_name(original_name)
    cache_key = (normalized, election_date)
    if cache_key in cache:
        return cache[cache_key]

    # Query for existing election using normalized name for comparison
    normalized_name = normalize_election_name(original_name)
    result = await session.execute(
        select(Election).where(
            Election.name == normalized_name,
            Election.election_date == election_date,
            Election.deleted_at.is_(None),
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Backfill eligible_county/eligible_municipality if not yet set
        if county and not existing.eligible_county:
            existing.eligible_county = county.upper()
        if municipality and not existing.eligible_municipality:
            existing.eligible_municipality = municipality
        cache[cache_key] = existing.id
        return existing.id

    # Create new election — preserve original as source_name
    new_id = uuid.uuid4()
    stmt = pg_insert(Election.__table__).values(
        id=new_id,
        name=normalized_name,
        source_name=original_name,
        election_date=election_date,
        election_type=election_type or "general",
        district=original_name,
        source="manual",
        creation_method="manual",
        status="active",
        eligible_county=county.upper() if county else None,
        eligible_municipality=municipality,
    )
    await session.execute(stmt)
    await session.flush()

    cache[cache_key] = new_id
    logger.info(f"Created election: {election_name} ({election_date}) -> {new_id}")
    return new_id


async def _upsert_candidate_batch(
    session: AsyncSession,
    records: list[dict],
) -> tuple[int, int]:
    """Bulk upsert candidate records using PostgreSQL INSERT ... ON CONFLICT.

    Uses the unique constraint on ``(election_id, full_name)`` as the
    conflict target.

    Args:
        session: Database session.
        records: Prepared candidate record dicts.

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not records:
        return 0, 0

    total_inserted = 0
    total_updated = 0

    update_columns = [
        "party",
        "filing_status",
        "is_incumbent",
        "contest_name",
        "qualified_date",
        "occupation",
        "email",
        "home_county",
        "municipality",
        "import_job_id",
    ]

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Candidate.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candidate_election_name",
            set_={col: stmt.excluded[col] for col in update_columns},
        )
        # xmax = 0 identifies genuinely new rows (not updated via ON CONFLICT)
        stmt = stmt.returning(  # type: ignore[assignment]
            Candidate.__table__.c.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


async def _upsert_candidate_links(
    session: AsyncSession,
    links: list[dict],
) -> None:
    """Create or update candidate links (website URLs).

    For each link, does an upsert on (candidate_id, link_type).

    Args:
        session: Database session.
        links: List of dicts with candidate_id, link_type, url.
    """
    if not links:
        return

    for link in links:
        # Check if link already exists
        result = await session.execute(
            select(CandidateLink.id).where(
                CandidateLink.candidate_id == link["candidate_id"],
                CandidateLink.link_type == link["link_type"],
            )
        )
        existing_id = result.scalar_one_or_none()

        if existing_id is not None:
            # Update existing link
            from sqlalchemy import update

            await session.execute(update(CandidateLink).where(CandidateLink.id == existing_id).values(url=link["url"]))
        else:
            # Insert new link
            stmt = pg_insert(CandidateLink.__table__).values(
                id=uuid.uuid4(),
                candidate_id=link["candidate_id"],
                link_type=link["link_type"],
                url=link["url"],
            )
            await session.execute(stmt)


async def process_candidate_import(
    session: AsyncSession,
    job: ImportJob,
    file_path: Path,
    batch_size: int = 500,
) -> ImportJob:
    """Process a candidate JSONL file import with bulk upsert.

    Reads the JSONL file in batches, resolves elections, upserts candidates,
    and creates candidate links for website URLs.

    Args:
        session: Database session.
        job: The ImportJob to track progress.
        file_path: Path to the preprocessed JSONL file.
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
    needs_review_count = 0
    errors: list[dict] = []
    election_cache: dict[tuple[str, date], uuid.UUID] = {}

    try:
        chunk_offset = job.last_processed_offset or 0
        for chunk_idx, records in enumerate(parse_candidate_import_jsonl(file_path, batch_size)):
            if chunk_idx < chunk_offset:
                continue

            chunk_total = len(records)
            total += chunk_total

            # Separate valid and invalid records
            valid_records: list[dict] = []
            pending_links: list[dict] = []

            for record in records:
                parse_error = record.pop("_parse_error", None)
                if parse_error:
                    errors.append(
                        {
                            "candidate_name": record.get("candidate_name", "unknown"),
                            "error": parse_error,
                        }
                    )
                    continue

                # Track and remove internal fields
                if record.pop("_needs_manual_review", None):
                    needs_review_count += 1
                record.pop("district_type", None)
                record.pop("district_identifier", None)
                record.pop("district_party", None)

                # Resolve election
                election_name = record.get("election_name", "")
                election_date_val = record.get("election_date")
                election_type = record.get("election_type")

                if not isinstance(election_date_val, date):
                    errors.append(
                        {
                            "candidate_name": record.get("candidate_name", "unknown"),
                            "error": f"Invalid election_date type: {type(election_date_val).__name__}",
                        }
                    )
                    continue

                try:
                    election_id = await _resolve_election(
                        session,
                        election_name,
                        election_date_val,
                        election_type,
                        election_cache,
                        county=record.get("county"),
                        municipality=record.get("municipality"),
                    )
                except Exception as e:
                    errors.append(
                        {
                            "candidate_name": record.get("candidate_name", "unknown"),
                            "error": f"Election resolution failed: {e}",
                        }
                    )
                    continue

                # Extract website before building DB record
                website = record.pop("website", None)

                # Build candidate record for upsert
                candidate_name = record.get("candidate_name", "")
                filing_status = record.get("filing_status") or "qualified"
                # Ensure filing_status is valid for the DB constraint
                if filing_status not in ("qualified", "withdrawn", "disqualified", "write_in"):
                    filing_status = "qualified"

                is_incumbent = record.get("is_incumbent")
                if is_incumbent is None:
                    is_incumbent = False

                db_record = {
                    "id": uuid.uuid4(),
                    "election_id": election_id,
                    "full_name": candidate_name,
                    "party": record.get("party"),
                    "filing_status": filing_status,
                    "is_incumbent": is_incumbent,
                    "contest_name": record.get("contest_name"),
                    "qualified_date": record.get("qualified_date"),
                    "occupation": record.get("occupation"),
                    "email": record.get("email"),
                    "home_county": record.get("county"),
                    "municipality": record.get("municipality"),
                    "import_job_id": job.id,
                }

                valid_records.append(db_record)

                # Queue website link if present
                if website:
                    pending_links.append(
                        {
                            "candidate_name": candidate_name,
                            "election_id": election_id,
                            "link_type": "website",
                            "url": website,
                        }
                    )

            # Deduplicate by (election_id, full_name) — keep last occurrence
            seen: dict[tuple, int] = {}
            for idx, rec in enumerate(valid_records):
                seen[(rec["election_id"], rec["full_name"])] = idx
            valid_records = [valid_records[i] for i in sorted(seen.values())]

            # Upsert candidates
            chunk_inserted, chunk_updated = await _upsert_candidate_batch(session, valid_records)
            inserted += chunk_inserted
            updated_count += chunk_updated

            # Resolve candidate links (need actual candidate IDs from DB)
            if pending_links:
                for link_info in pending_links:
                    # Look up the candidate ID by (election_id, full_name)
                    result = await session.execute(
                        select(Candidate.id).where(
                            Candidate.election_id == link_info["election_id"],
                            Candidate.full_name == link_info["candidate_name"],
                        )
                    )
                    candidate_id = result.scalar_one_or_none()
                    if candidate_id:
                        await _upsert_candidate_links(
                            session,
                            [
                                {
                                    "candidate_id": candidate_id,
                                    "link_type": link_info["link_type"],
                                    "url": link_info["url"],
                                }
                            ],
                        )

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
        job.records_needs_review = needs_review_count
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            f"Candidate import completed: {total} total, {succeeded} succeeded, "
            f"{failed} failed, {inserted} inserted, {updated_count} updated, "
            f"{needs_review_count} needs review"
        )

    except Exception:
        await session.rollback()
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    return job
