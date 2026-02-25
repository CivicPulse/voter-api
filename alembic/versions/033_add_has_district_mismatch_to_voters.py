"""Add has_district_mismatch column to voters table.

Revision ID: 033
Revises: 032
Create Date: 2026-02-25

Adds a nullable boolean ``has_district_mismatch`` column with an index for
efficient filtering.  Backfills from the latest completed analysis run if one
exists.
"""

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add has_district_mismatch column and backfill from latest analysis run."""
    op.add_column("voters", sa.Column("has_district_mismatch", sa.Boolean(), nullable=True))
    op.create_index("ix_voters_has_district_mismatch", "voters", ["has_district_mismatch"])

    # Backfill from the latest completed analysis run (if one exists)
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE voters v
            SET has_district_mismatch = (ar.match_status != 'match')
            FROM analysis_results ar
            JOIN analysis_runs run ON ar.analysis_run_id = run.id
            WHERE ar.voter_id = v.id
              AND run.id = (
                SELECT id FROM analysis_runs
                WHERE status = 'completed'
                ORDER BY completed_at DESC LIMIT 1
              )
        """)
    )


def downgrade() -> None:
    """Remove has_district_mismatch column."""
    op.drop_index("ix_voters_has_district_mismatch", table_name="voters")
    op.drop_column("voters", "has_district_mismatch")
