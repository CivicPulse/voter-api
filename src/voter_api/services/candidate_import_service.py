"""Candidate import service — orchestrates candidate JSONL import with upsert and election resolution."""

import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.candidate_importer import parse_candidate_import_jsonl
from voter_api.models.candidacy import Candidacy
from voter_api.models.candidate import Candidate, CandidateLink
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob

# Sub-batch size for candidate upsert: ~15 columns * 500 rows = 7,500 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

# Pattern matching trailing party markers like (R), (D), (NP), (I)
_PARTY_MARKER_RE = re.compile(r"\s*\([RDNPI]+\)\s*\Z")


def _normalize_election_name(name: str) -> str:
    """Normalize an election name for deduplication lookups.

    Applies the library-level normalizations (dash replacement, date
    standardization, abbreviation expansion) then strips trailing party
    markers such as ``(R)``, ``(D)``, ``(NP)``, ``(I)``, collapses
    whitespace, and lowercases the result.

    This is the single source of truth for election name normalization
    within the candidate import pipeline — used for both cache keys and
    DB queries to prevent cache misses from divergent normalization.

    Args:
        name: Raw election/contest name.

    Returns:
        Normalized lowercase name suitable for cache key comparison.
    """
    from voter_api.lib.election_name_normalizer import (
        normalize_election_name as _lib_normalize,
    )

    # Apply library normalizations first (dashes, dates, abbreviations)
    lib_normalized = _lib_normalize(name) or name
    # Then strip party markers
    stripped = _PARTY_MARKER_RE.sub("", lib_normalized)
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
    cache: dict[tuple[str, date, str, str], uuid.UUID],
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
    cache_key = (normalized, election_date, (county or "").upper(), municipality or "")
    if cache_key in cache:
        return cache[cache_key]

    # Query for existing election using case-insensitive comparison with the
    # same normalization used for cache keys (party markers stripped, lowered).
    result = await session.execute(
        select(Election).where(
            func.lower(Election.name) == normalized,
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

    # Create new election — preserve original as source_name.
    # Store the party-stripped, library-normalized name (preserving case).
    display_name = _PARTY_MARKER_RE.sub("", original_name).strip()
    from voter_api.lib.election_name_normalizer import (
        normalize_election_name as _lib_normalize,
    )

    stored_name = _lib_normalize(display_name) or display_name
    new_id = uuid.uuid4()
    stmt = pg_insert(Election).values(
        id=new_id,
        name=stored_name,
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
) -> tuple[int, int, list[uuid.UUID]]:
    """Bulk upsert candidate records using PostgreSQL INSERT ... ON CONFLICT.

    Uses the unique constraint on ``(election_id, full_name)`` as the
    conflict target.

    Args:
        session: Database session.
        records: Prepared candidate record dicts.

    Returns:
        Tuple of (inserted_count, updated_count, resolved_ids) where
        resolved_ids contains the actual database IDs (in input order)
        from the RETURNING clause.
    """
    if not records:
        return 0, 0, []

    total_inserted = 0
    total_updated = 0
    all_ids: list[uuid.UUID] = []

    # Columns that are always overwritten on conflict
    overwrite_columns = [
        "filing_status",
        "is_incumbent",
        "import_job_id",
    ]
    # Nullable columns: use COALESCE so a sparse re-import with None
    # does not erase richer existing data.
    coalesce_columns = [
        "party",
        "contest_name",
        "qualified_date",
        "occupation",
        "email",
        "home_county",
        "municipality",
    ]

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Candidate).values(batch)
        update_set: dict = {col: stmt.excluded[col] for col in overwrite_columns}
        for col in coalesce_columns:
            update_set[col] = func.coalesce(stmt.excluded[col], Candidate.__table__.c[col])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candidate_election_name",
            set_=update_set,
        )
        # xmax = 0 identifies genuinely new rows (not updated via ON CONFLICT).
        # Also return election_id and full_name for ID resolution.
        stmt = stmt.returning(  # type: ignore[assignment]
            Candidate.__table__.c.id,
            Candidate.__table__.c.election_id,
            Candidate.__table__.c.full_name,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        # Build lookup by (election_id, full_name) -> resolved DB id
        id_lookup: dict[tuple, uuid.UUID] = {}
        for row in rows:
            id_lookup[(row.election_id, row.full_name)] = row.id

        # Preserve input order for resolved IDs
        for rec in batch:
            key = (rec["election_id"], rec["full_name"])
            all_ids.append(id_lookup[key])

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated, all_ids


async def _upsert_candidate_links(
    session: AsyncSession,
    links: list[dict],
) -> None:
    """Create or update candidate links (website URLs).

    Uses ``INSERT ... ON CONFLICT DO UPDATE`` on the
    ``(candidate_id, link_type)`` unique constraint for batch upsert
    instead of per-link delete+insert.

    Args:
        session: Database session.
        links: List of dicts with candidate_id, link_type, url,
            and optionally label.
    """
    if not links:
        return

    # Prepare records with UUIDs for new rows
    values = []
    for link in links:
        values.append(
            {
                "id": uuid.uuid4(),
                "candidate_id": link["candidate_id"],
                "link_type": link["link_type"],
                "url": link["url"],
                "label": link.get("label"),
            }
        )

    for i in range(0, len(values), _UPSERT_SUB_BATCH):
        batch = values[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(CandidateLink).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candidate_link_type",
            set_={
                "url": stmt.excluded.url,
                "label": stmt.excluded.label,
            },
        )
        await session.execute(stmt)


async def _upsert_candidacy_batch(
    session: AsyncSession,
    records: list[dict],
) -> None:
    """Create or update candidacy records for imported candidates.

    Uses the unique constraint on ``(candidate_id, election_id)`` as the
    conflict target. Contest-specific fields from the candidate import are
    copied to the candidacy junction table.

    Args:
        session: Database session.
        records: List of dicts with candidate_id, election_id, and
            contest-specific fields.
    """
    if not records:
        return

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Candidacy).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candidacy_candidate_election",
            set_={
                "party": func.coalesce(stmt.excluded.party, Candidacy.__table__.c.party),
                "filing_status": stmt.excluded.filing_status,
                "is_incumbent": stmt.excluded.is_incumbent,
                "contest_name": func.coalesce(stmt.excluded.contest_name, Candidacy.__table__.c.contest_name),
                "qualified_date": func.coalesce(stmt.excluded.qualified_date, Candidacy.__table__.c.qualified_date),
                "occupation": func.coalesce(stmt.excluded.occupation, Candidacy.__table__.c.occupation),
                "home_county": func.coalesce(stmt.excluded.home_county, Candidacy.__table__.c.home_county),
                "municipality": func.coalesce(stmt.excluded.municipality, Candidacy.__table__.c.municipality),
                "import_job_id": stmt.excluded.import_job_id,
            },
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
    election_cache: dict[tuple[str, date, str, str], uuid.UUID] = {}

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
                    logger.warning(
                        "Rewriting invalid filing_status '{}' to 'qualified' for candidate '{}'",
                        filing_status,
                        candidate_name,
                    )
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

            # Upsert candidates and capture resolved IDs from RETURNING clause
            chunk_inserted, chunk_updated, resolved_ids = await _upsert_candidate_batch(session, valid_records)
            inserted += chunk_inserted
            updated_count += chunk_updated

            # Build lookup from (election_id, full_name) -> resolved DB id
            resolved_id_lookup: dict[tuple, uuid.UUID] = {}
            for rec, resolved_id in zip(valid_records, resolved_ids, strict=True):
                resolved_id_lookup[(rec["election_id"], rec["full_name"])] = resolved_id

            # Create candidacy records using resolved IDs (no extra queries)
            if valid_records:
                candidacy_records: list[dict] = []
                for rec in valid_records:
                    if rec.get("election_id") is None:
                        continue
                    cand_id = resolved_id_lookup.get((rec["election_id"], rec["full_name"]))
                    if cand_id:
                        candidacy_records.append(
                            {
                                "id": uuid.uuid4(),
                                "candidate_id": cand_id,
                                "election_id": rec["election_id"],
                                "party": rec.get("party"),
                                "filing_status": rec.get("filing_status", "qualified"),
                                "is_incumbent": rec.get("is_incumbent", False),
                                "contest_name": rec.get("contest_name"),
                                "qualified_date": rec.get("qualified_date"),
                                "occupation": rec.get("occupation"),
                                "home_county": rec.get("home_county"),
                                "municipality": rec.get("municipality"),
                                "import_job_id": job.id,
                            }
                        )
                if candidacy_records:
                    await _upsert_candidacy_batch(session, candidacy_records)

            # Resolve candidate links using the same lookup (no extra queries)
            if pending_links:
                resolved_links: list[dict] = []
                for link_info in pending_links:
                    cand_id = resolved_id_lookup.get((link_info["election_id"], link_info["candidate_name"]))
                    if cand_id:
                        resolved_links.append(
                            {
                                "candidate_id": cand_id,
                                "link_type": link_info["link_type"],
                                "url": link_info["url"],
                            }
                        )
                if resolved_links:
                    await _upsert_candidate_links(session, resolved_links)

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


# --- JSONL person-entity import (new pipeline) ---


_CANDIDATE_JSONL_COALESCE = [
    "bio",
    "photo_url",
    "email",
    "home_county",
    "municipality",
]


def _prepare_candidate_jsonl_record(record: dict) -> dict:
    """Prepare a validated CandidateJSONL record for DB insertion.

    Maps person-level JSONL fields to the Candidate model columns.
    Contest-specific fields are NOT present -- those live on CandidacyJSONL.

    Args:
        record: Validated record dict from Pydantic model_dump().

    Returns:
        Dict suitable for pg_insert().values().
    """
    db_record: dict = {}

    # UUID
    val = record.get("id")
    if val is not None:
        db_record["id"] = uuid.UUID(val) if isinstance(val, str) else val

    # String fields
    for field in ["full_name", "bio", "photo_url", "email", "home_county", "municipality"]:
        if field in record and record[field] is not None:
            db_record[field] = record[field]

    # External IDs (JSONB)
    if "external_ids" in record and record["external_ids"]:
        db_record["external_ids"] = record["external_ids"]

    return db_record


async def _upsert_candidate_jsonl_batch(
    session: AsyncSession,
    records: list[dict],
) -> tuple[int, int]:
    """Bulk upsert candidate person records by UUID primary key.

    This is for the new JSONL pipeline where candidates are person entities
    without election_id. Uses conflict on the 'id' column (PK).

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

    # Normalize: ensure every record has the same set of keys so that
    # PostgreSQL INSERT ... ON CONFLICT DO UPDATE gets uniform columns.
    all_keys: set[str] = set()
    for r in records:
        all_keys.update(r.keys())
    normalized_records = [dict.fromkeys(all_keys) | r for r in records]

    # Always-overwrite fields
    overwrite_fields = ["full_name"]
    # COALESCE fields: preserve richer existing data
    coalesce_fields = _CANDIDATE_JSONL_COALESCE

    for i in range(0, len(normalized_records), _UPSERT_SUB_BATCH):
        batch = normalized_records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Candidate).values(batch)
        update_set: dict = {}
        for col in overwrite_fields:
            if col in all_keys:
                update_set[col] = stmt.excluded[col]
        for col in coalesce_fields:
            if col in all_keys:
                update_set[col] = func.coalesce(stmt.excluded[col], Candidate.__table__.c[col])
        # external_ids: merge via COALESCE
        if "external_ids" in all_keys:
            update_set["external_ids"] = func.coalesce(stmt.excluded.external_ids, Candidate.__table__.c.external_ids)

        if not update_set:
            continue

        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
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

    return total_inserted, total_updated


async def import_candidates_jsonl(
    session: AsyncSession,
    records: list[dict],
    *,
    dry_run: bool = False,
) -> dict:
    """Import candidate person-entity records from validated CandidateJSONL data.

    This is distinct from process_candidate_import which handles the legacy
    preprocessed JSONL format with election resolution. This function handles
    the new JSONL pipeline where candidates are person entities with UUIDs.

    Args:
        session: Database session.
        records: List of validated record dicts (from read_jsonl).
        dry_run: If True, report what would happen without writing.

    Returns:
        Summary dict with inserted/updated/errors counts.
    """
    prepared = []
    all_links: list[dict] = []
    errors: list[dict] = []

    for record in records:
        try:
            db_record = _prepare_candidate_jsonl_record(record)
            prepared.append(db_record)

            # Extract links for upsert (link_type, url, label)
            candidate_id = db_record.get("id")
            for link in record.get("links", []):
                link_type = link.get("link_type") or link.get("type")
                url = link.get("url", "")
                label = link.get("label")
                if candidate_id and link_type and url:
                    all_links.append(
                        {
                            "candidate_id": candidate_id,
                            "link_type": link_type,
                            "url": url,
                            "label": label,
                        }
                    )
        except Exception as e:
            errors.append({"id": str(record.get("id", "unknown")), "error": str(e)})

    if dry_run:
        record_ids = [r["id"] for r in prepared]
        existing_result = await session.execute(select(Candidate.id).where(Candidate.id.in_(record_ids)))
        existing_ids = set(existing_result.scalars().all())

        would_insert = sum(1 for r in prepared if r["id"] not in existing_ids)
        would_update = sum(1 for r in prepared if r["id"] in existing_ids)

        return {
            "would_insert": would_insert,
            "would_update": would_update,
            "errors": errors,
        }

    inserted, updated = await _upsert_candidate_jsonl_batch(session, prepared)

    # Upsert links extracted from the JSONL records
    if all_links:
        await _upsert_candidate_links(session, all_links)

    await session.commit()

    logger.info(f"Candidates JSONL import: {inserted} inserted, {updated} updated, {len(errors)} errors")
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": 0,
        "errors": errors,
    }
