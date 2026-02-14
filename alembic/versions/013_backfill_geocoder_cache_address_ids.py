"""backfill geocoder_cache address_id from existing normalized addresses

Revision ID: 013
Revises: fd115a563390
Create Date: 2026-02-13

Idempotent data migration: inserts unique normalized_address values from
geocoder_cache into the addresses table (components left NULL), then sets
the address_id FK on geocoder_cache rows. Safe to re-run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "fd115a563390"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill addresses table from geocoder_cache and link FK.

    Uses raw SQL because this is a data-only migration operating on existing
    tables — no ORM models are needed. This is an intentional exception to
    the "no raw SQL" convention documented in CLAUDE.md.
    """
    bind = op.get_bind()

    # Insert DISTINCT normalized addresses from geocoder_cache into addresses table,
    # skipping any that already exist (ON CONFLICT DO NOTHING).
    result = bind.execute(
        sa.text("""
        INSERT INTO addresses (id, normalized_address, created_at, updated_at)
        SELECT gen_random_uuid(), sub.normalized_address, now(), now()
        FROM (
            SELECT DISTINCT gc.normalized_address
            FROM geocoder_cache gc
            WHERE gc.address_id IS NULL
              AND gc.normalized_address IS NOT NULL
        ) sub
        ON CONFLICT (normalized_address) DO NOTHING
        """)
    )
    print(f"  -> Inserted {result.rowcount} new address rows")  # noqa: T201

    # Set address_id FK on geocoder_cache rows that are still NULL
    result = bind.execute(
        sa.text("""
        UPDATE geocoder_cache gc
        SET address_id = a.id
        FROM addresses a
        WHERE gc.normalized_address = a.normalized_address
          AND gc.address_id IS NULL
        """)
    )
    print(f"  -> Updated {result.rowcount} geocoder_cache rows with address_id")  # noqa: T201


def downgrade() -> None:
    raise NotImplementedError(
        "Irreversible data migration: cannot distinguish address_id values "
        "set by this migration from those set by the application. "
        "Restore from backup if rollback is needed."
    )
