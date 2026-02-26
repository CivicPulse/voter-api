"""Add soft-delete, source field, and nullable data_source_url to elections.

Adds deleted_at (soft-delete), source (sos_feed/manual/linked), and
makes data_source_url nullable to support manual elections without feed URLs.

This migration is irreversible once rows exist with NULL data_source_url.
Downgrade requires restoring from backup.

Revision ID: 039
Revises: 038
Create Date: 2026-02-26
"""

import sqlalchemy as sa
from alembic import op

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("elections", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_elections_deleted_at", "elections", ["deleted_at"])
    op.add_column(
        "elections",
        sa.Column("source", sa.String(20), nullable=False, server_default="sos_feed"),
    )
    op.create_check_constraint(
        "ck_election_source",
        "elections",
        "source IN ('sos_feed', 'manual', 'linked')",
    )
    op.create_index("idx_elections_source", "elections", ["source"])
    op.alter_column("elections", "data_source_url", nullable=True)


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade from revision 039 is not supported because "
        "elections.data_source_url may contain NULL values and cannot be "
        "safely made NOT NULL again."
    )
