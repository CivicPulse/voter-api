"""Add soft-delete, source field, and nullable data_source_url to elections.

Adds deleted_at (soft-delete), source (sos_feed/manual/linked), and
makes data_source_url nullable to support manual elections without feed URLs.

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
    # This migration makes elections.data_source_url nullable to support manual
    # elections without feed URLs. After applying it, the database may contain
    # rows where data_source_url IS NULL, so attempting to set the column back
    # to NOT NULL would fail on PostgreSQL. Downgrade is non-reversible once
    # manual elections exist.
    raise RuntimeError(
        "Downgrade from revision 039 is not supported because "
        "elections.data_source_url may contain NULL values and cannot be "
        "safely made NOT NULL again."
    )
    op.alter_column("elections", "data_source_url", nullable=False)  # unreachable; kept for reference
    op.drop_index("idx_elections_source", table_name="elections")
    op.drop_constraint("ck_election_source", "elections", type_="check")
    op.drop_column("elections", "source")
    op.drop_index("ix_elections_deleted_at", table_name="elections")
    op.drop_column("elections", "deleted_at")
