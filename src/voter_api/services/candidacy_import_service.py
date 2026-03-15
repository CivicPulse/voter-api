"""Candidacy JSONL import service.

Reads validated CandidacyJSONL records and upserts them into the
candidacies table using PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
"""

import uuid
from typing import Any

from loguru import logger
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.candidacy import Candidacy

# Sub-batch size: ~12 columns * 500 rows = 6,000 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

# Columns excluded from the ON CONFLICT UPDATE set
_EXCLUDE_COLUMNS = frozenset({"id", "created_at"})

# Columns that use COALESCE to preserve richer existing data
_COALESCE_COLUMNS = [
    "party",
    "contest_name",
    "qualified_date",
    "occupation",
    "home_county",
    "municipality",
    "sos_ballot_option_id",
]


async def _upsert_candidacy_batch(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    """Bulk upsert candidacy records.

    Args:
        session: Database session.
        records: Prepared record dicts.

    Returns:
        Tuple of (inserted_count, updated_count).
    """
    if not records:
        return 0, 0

    total_inserted = 0
    total_updated = 0

    for i in range(0, len(records), _UPSERT_SUB_BATCH):
        batch = records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(Candidacy).values(batch)

        # Build update set: overwrite always-update fields, COALESCE nullable ones
        update_set: dict[str, Any] = {
            "filing_status": stmt.excluded.filing_status,
            "is_incumbent": stmt.excluded.is_incumbent,
            "ballot_order": stmt.excluded.ballot_order,
        }
        for col in _COALESCE_COLUMNS:
            if col in batch[0]:
                update_set[col] = func.coalesce(stmt.excluded[col], Candidacy.__table__.c[col])

        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_=update_set,
        )
        stmt = stmt.returning(  # type: ignore[assignment]
            Candidacy.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


def _prepare_record(record: dict[str, Any]) -> dict[str, Any]:
    """Prepare a validated CandidacyJSONL record dict for database insertion.

    Args:
        record: Validated record dict from Pydantic model_dump().

    Returns:
        Dict suitable for pg_insert().values().
    """
    db_record: dict[str, Any] = {}

    # UUID fields
    for uuid_field in ["id", "candidate_id", "election_id"]:
        if uuid_field in record and record[uuid_field] is not None:
            val = record[uuid_field]
            db_record[uuid_field] = uuid.UUID(val) if isinstance(val, str) else val

    # String/nullable fields
    string_fields = [
        "party",
        "occupation",
        "contest_name",
        "home_county",
        "municipality",
        "sos_ballot_option_id",
    ]
    for field in string_fields:
        if field in record:
            db_record[field] = record[field]

    # Enum field -> string value
    if "filing_status" in record and record["filing_status"] is not None:
        val = record["filing_status"]
        db_record["filing_status"] = val.value if hasattr(val, "value") else str(val)
    else:
        db_record["filing_status"] = "qualified"

    # Boolean field
    db_record["is_incumbent"] = record.get("is_incumbent", False)

    # Integer field
    if "ballot_order" in record:
        db_record["ballot_order"] = record["ballot_order"]

    # Date field
    if "qualified_date" in record:
        db_record["qualified_date"] = record["qualified_date"]

    return db_record


async def import_candidacies(
    session: AsyncSession,
    records: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import candidacy records from validated JSONL data.

    Args:
        session: Database session.
        records: List of validated record dicts (from read_jsonl).
        dry_run: If True, report what would happen without writing.

    Returns:
        Summary dict with keys:
        - inserted, updated, skipped, errors (normal mode)
        - would_insert, would_update (dry-run mode)
    """
    prepared = []
    errors: list[dict[str, Any]] = []

    for record in records:
        try:
            db_record = _prepare_record(record)
            prepared.append(db_record)
        except Exception as e:
            errors.append({"id": str(record.get("id", "unknown")), "error": str(e)})

    if dry_run:
        record_ids = [r["id"] for r in prepared]
        existing_result = await session.execute(select(Candidacy.id).where(Candidacy.id.in_(record_ids)))
        existing_ids = set(existing_result.scalars().all())

        would_insert = sum(1 for r in prepared if r["id"] not in existing_ids)
        would_update = sum(1 for r in prepared if r["id"] in existing_ids)

        logger.info(f"Dry-run: {would_insert} would be inserted, {would_update} would be updated")
        return {
            "would_insert": would_insert,
            "would_update": would_update,
            "errors": errors,
        }

    inserted, updated = await _upsert_candidacy_batch(session, prepared)
    await session.commit()

    logger.info(f"Candidacies import: {inserted} inserted, {updated} updated, {len(errors)} errors")
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": 0,
        "errors": errors,
    }
