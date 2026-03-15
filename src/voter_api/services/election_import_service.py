"""Election JSONL import service.

Reads validated ElectionJSONL records and upserts them into the
elections table using PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
"""

import uuid
from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.election import Election

# Sub-batch size: ~25 columns * 500 rows = 12,500 params (under 32,767 limit)
_UPSERT_SUB_BATCH = 500

# Well-known placeholder UUID emitted by the converter when election_event_id
# cannot be resolved at conversion time. Treat as None to avoid FK violations.
_PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"

# Columns excluded from the ON CONFLICT UPDATE set
_EXCLUDE_COLUMNS = frozenset({"id", "created_at"})


async def _upsert_election_batch(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    """Bulk upsert election records.

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

        stmt = pg_insert(Election).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={col: stmt.excluded[col] for col in update_columns},
        )
        stmt = stmt.returning(  # type: ignore[assignment]
            Election.id,
            literal_column("(xmax = 0)::int").label("is_insert"),
        )

        result = await session.execute(stmt)
        rows = result.all()

        batch_inserted = sum(row.is_insert for row in rows)
        total_inserted += batch_inserted
        total_updated += len(rows) - batch_inserted

    return total_inserted, total_updated


def _prepare_record(record: dict[str, Any]) -> dict[str, Any]:
    """Prepare a validated ElectionJSONL record dict for database insertion.

    Args:
        record: Validated record dict from Pydantic model_dump().

    Returns:
        Dict suitable for pg_insert().values().
    """
    db_record: dict[str, Any] = {}

    # Direct field mappings
    direct_fields = [
        "id",
        "name",
        "election_date",
        "district",
        "data_source_url",
        "source_name",
        "source",
        "ballot_item_id",
        "status",
        "last_refreshed_at",
        "refresh_interval_seconds",
        "eligible_county",
        "eligible_municipality",
    ]

    for field in direct_fields:
        if field in record and record[field] is not None:
            val = record[field]
            if field == "id" and isinstance(val, str):
                val = uuid.UUID(val)
            elif field == "election_date" and isinstance(val, str):
                val = date.fromisoformat(val)
            db_record[field] = val

    # UUID fields
    for uuid_field in ["election_event_id", "boundary_id"]:
        if uuid_field in record and record[uuid_field] is not None:
            val = record[uuid_field]
            # Skip well-known placeholder UUID (converter emits this when
            # election_event_id can't be resolved at conversion time)
            str_val = str(val)
            if str_val == _PLACEHOLDER_UUID:
                continue
            db_record[uuid_field] = uuid.UUID(val) if isinstance(val, str) else val

    # Enum fields -> string values
    for enum_field in ["election_type", "election_stage"]:
        if enum_field in record and record[enum_field] is not None:
            val = record[enum_field]
            db_record[enum_field] = val.value if hasattr(val, "value") else str(val)

    # name_sos maps to source_name if source_name not already set
    if "name_sos" in record and record["name_sos"] and "source_name" not in db_record:
        db_record["source_name"] = record["name_sos"]

    # boundary_type maps to district_type
    if "boundary_type" in record and record["boundary_type"] is not None:
        db_record["district_type"] = record["boundary_type"]

    # district_identifier
    if "district_identifier" in record and record["district_identifier"] is not None:
        db_record["district_identifier"] = record["district_identifier"]

    # district_party
    if "district_party" in record and record["district_party"] is not None:
        db_record["district_party"] = record["district_party"]

    # Required fields with defaults
    db_record.setdefault("district", db_record.get("name", ""))
    db_record.setdefault("source", "manual")
    db_record.setdefault("creation_method", "manual")
    db_record.setdefault("status", "active")
    db_record.setdefault("election_type", "general")

    return db_record


async def import_elections(
    session: AsyncSession,
    records: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Import election records from validated JSONL data.

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
        existing_result = await session.execute(select(Election.id).where(Election.id.in_(record_ids)))
        existing_ids = set(existing_result.scalars().all())

        would_insert = sum(1 for r in prepared if r["id"] not in existing_ids)
        would_update = sum(1 for r in prepared if r["id"] in existing_ids)

        logger.info(f"Dry-run: {would_insert} would be inserted, {would_update} would be updated")
        return {
            "would_insert": would_insert,
            "would_update": would_update,
            "errors": errors,
        }

    inserted, updated = await _upsert_election_batch(session, prepared)
    await session.commit()

    logger.info(f"Elections import: {inserted} inserted, {updated} updated, {len(errors)} errors")
    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": 0,
        "errors": errors,
    }
