"""Add pg_trgm GIN indexes for voter name search performance.

Revision ID: 023
Revises: 022
Create Date: 2026-02-20

Enables the pg_trgm extension and adds GIN trigram indexes on voter name fields
(first_name, last_name, middle_name). These indexes make substring ILIKE queries
efficient at scale (~7M Georgia voter records). Without them, combined name
searches via the ``q`` parameter fall back to sequential scans.

Note: on an already-populated production database, consider running these
``CREATE INDEX`` statements manually with ``CONCURRENTLY`` to avoid table locks.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_voters_first_name_trgm ON voters USING GIN (first_name gin_trgm_ops)")
    op.execute("CREATE INDEX ix_voters_last_name_trgm ON voters USING GIN (last_name gin_trgm_ops)")
    op.execute("CREATE INDEX ix_voters_middle_name_trgm ON voters USING GIN (middle_name gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_voters_first_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_voters_last_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_voters_middle_name_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
