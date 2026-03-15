"""Election event JSONL import service.

Reads validated ElectionEventJSONL records and upserts them into the
election_events table using PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
"""

import uuid
from typing import Any

from loguru import logger
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.election_event import ElectionEvent

# Sub-batch size: ~15 columns * 500 rows = 7,500 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

# Columns excluded from the ON CONFLICT UPDATE set
_EXCLUDE_COLUMNS = frozenset({"id", "created_at"})


async def _upsert_election_event_batch(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    """Bulk upsert election event records.

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

    # Compute the union of all column keys across records so every record
    # has the same set of keys. PostgreSQL requires INSERT ... VALUES with
    # uniform columns when using ON CONFLICT DO UPDATE (excluded.<col>
    # references are only valid if the column was present in the INSERT).
    all_keys: set[str] = set()
    for r in records:
        all_keys.update(r.keys())
    normalized_records = [dict.fromkeys(all_keys) | r for r in records]

    update_columns = sorted(all_keys - _EXCLUDE_COLUMNS)

    for i in range(0, len(normalized_records), _UPSERT_SUB_BATCH):
        batch = normalized_records[i : i + _UPSERT_SUB_BATCH]

        stmt = pg_insert(ElectionEvent).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={col: stmt.excluded[col] for col in update_columns},
        )
        stmt = stmt.returning(  # type: ignore[assignment]
            ElectionEvent.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


def _prepare_record(record: dict[str, Any]) -> dict[str, Any]:
    """Prepare a validated JSONL record dict for database insertion.

    Maps JSONL schema fields to ElectionEvent model columns. Removes
    schema_version and any fields not present on the ORM model.

    Args:
        record: Validated record dict from Pydantic model_dump().

    Returns:
        Dict suitable for pg_insert().values().
    """
    db_record: dict[str, Any] = {}

    # Direct field mappings (JSONL field name == DB column name)
    direct_fields = [
        "id",
        "event_date",
        "event_name",
        "event_type",
        "registration_deadline",
        "early_voting_start",
        "early_voting_end",
        "absentee_request_deadline",
        "qualifying_start",
        "qualifying_end",
        "data_source_url",
        "last_refreshed_at",
        "refresh_interval_seconds",
    ]

    for field in direct_fields:
        if field in record and record[field] is not None:
            val = record[field]
            # Ensure UUID is a proper uuid object
            if field == "id" and isinstance(val, str):
                val = uuid.UUID(val)
            db_record[field] = val

    # Map election_stage if present (JSONL has it as a separate concept)
    if "election_stage" in record and record["election_stage"] is not None:
        stage = record["election_stage"]
        db_record["election_stage"] = stage.value if hasattr(stage, "value") else str(stage)

    # Ensure event_type is a string value
    if "event_type" in db_record:
        et = db_record["event_type"]
        db_record["event_type"] = et.value if hasattr(et, "value") else str(et)

    return db_record


async def import_election_events(
    session: AsyncSession,
    records: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import election event records from validated JSONL data.

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
        # Check which IDs already exist
        record_ids = [r["id"] for r in prepared]
        existing_result = await session.execute(select(ElectionEvent.id).where(ElectionEvent.id.in_(record_ids)))
        existing_ids = set(existing_result.scalars().all())

        would_insert = sum(1 for r in prepared if r["id"] not in existing_ids)
        would_update = sum(1 for r in prepared if r["id"] in existing_ids)

        logger.info(f"Dry-run: {would_insert} would be inserted, {would_update} would be updated")
        return {
            "would_insert": would_insert,
            "would_update": would_update,
            "errors": errors,
        }

    inserted, updated = await _upsert_election_event_batch(session, prepared)
    await session.commit()

    logger.info(f"Election events import: {inserted} inserted, {updated} updated, {len(errors)} errors")
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": 0,
        "errors": errors,
    }
