"""backfill geocoder_cache address_id from existing normalized addresses

Revision ID: 013
Revises: fd115a563390
Create Date: 2026-02-13

Idempotent data migration: for each geocoder_cache row with address_id IS NULL,
parse components from normalized_address, upsert into the addresses table, then
set the FK. Safe to re-run.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "fd115a563390"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Insert unique normalized addresses from geocoder_cache into addresses table,
    # skipping any that already exist (ON CONFLICT DO NOTHING).
    op.execute(
        """
        INSERT INTO addresses (id, normalized_address, created_at, updated_at)
        SELECT gen_random_uuid(), gc.normalized_address, now(), now()
        FROM geocoder_cache gc
        WHERE gc.address_id IS NULL
          AND gc.normalized_address IS NOT NULL
        ON CONFLICT (normalized_address) DO NOTHING
        """
    )

    # Set address_id FK on geocoder_cache rows that are still NULL
    op.execute(
        """
        UPDATE geocoder_cache gc
        SET address_id = a.id
        FROM addresses a
        WHERE gc.normalized_address = a.normalized_address
          AND gc.address_id IS NULL
        """
    )


def downgrade() -> None:
    # Clear address_id FKs that were set by this migration.
    # Does not delete address rows (they may be referenced by other FKs).
    op.execute(
        """
        UPDATE geocoder_cache
        SET address_id = NULL
        WHERE address_id IS NOT NULL
        """
    )
