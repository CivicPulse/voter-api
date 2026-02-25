"""fix duplicate primary geocoded locations

For voters with multiple is_primary=true geocoded locations, keep the one
with the highest confidence score (tie-break: most recent geocoded_at) and
demote the rest to is_primary=false.

Revision ID: 034
Revises: 033
Create Date: 2026-02-25
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "034"
down_revision: str | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # For each voter with duplicate primaries, keep only the best one
    # (highest confidence, then most recent) and demote the rest.
    op.execute("""
        UPDATE geocoded_locations
        SET is_primary = false
        WHERE id IN (
            SELECT gl.id
            FROM geocoded_locations gl
            INNER JOIN (
                SELECT DISTINCT ON (voter_id) id AS keep_id, voter_id
                FROM geocoded_locations
                WHERE is_primary = true
                ORDER BY voter_id, confidence_score DESC, geocoded_at DESC
            ) best ON best.voter_id = gl.voter_id
            WHERE gl.is_primary = true
              AND gl.id != best.keep_id
        )
    """)


def downgrade() -> None:
    # Cannot reliably restore which locations were previously primary.
    # The upgrade is a data-quality fix; downgrade is a no-op.
    pass
