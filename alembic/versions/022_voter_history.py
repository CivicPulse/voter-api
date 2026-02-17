"""create voter_history table, add elections.creation_method and import_jobs counters

Revision ID: 022
Revises: 021
Create Date: 2026-02-17

Creates voter_history table for GA SoS voter participation history records.
Adds creation_method column to elections table to distinguish auto-created
elections. Adds records_skipped and records_unmatched counters to import_jobs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- voter_history table ---
    pg_uuid = sa.dialects.postgresql.UUID(as_uuid=True)
    op.create_table(
        "voter_history",
        sa.Column(
            "id",
            pg_uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("voter_registration_number", sa.String(20), nullable=False),
        sa.Column("county", sa.String(100), nullable=False),
        sa.Column("election_date", sa.Date, nullable=False),
        sa.Column("election_type", sa.String(50), nullable=False),
        sa.Column("normalized_election_type", sa.String(20), nullable=False),
        sa.Column("party", sa.String(50), nullable=True),
        sa.Column("ballot_style", sa.String(100), nullable=True),
        sa.Column("absentee", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("provisional", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("supplemental", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "import_job_id",
            pg_uuid,
            sa.ForeignKey("import_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "voter_registration_number",
            "election_date",
            "election_type",
            name="uq_voter_history_participation",
        ),
    )

    # Indexes for voter_history
    op.create_index("idx_voter_history_reg_num", "voter_history", ["voter_registration_number"])
    op.create_index("idx_voter_history_election_date", "voter_history", ["election_date"])
    op.create_index("idx_voter_history_election_type", "voter_history", ["election_type"])
    op.create_index("idx_voter_history_county", "voter_history", ["county"])
    op.create_index("idx_voter_history_import_job_id", "voter_history", ["import_job_id"])
    op.create_index("idx_voter_history_date_type", "voter_history", ["election_date", "normalized_election_type"])

    # --- elections.creation_method ---
    op.add_column("elections", sa.Column("creation_method", sa.String(20), nullable=False, server_default="manual"))
    op.create_index("idx_elections_creation_method", "elections", ["creation_method"])

    # --- import_jobs new counters ---
    op.add_column("import_jobs", sa.Column("records_skipped", sa.Integer, nullable=True))
    op.add_column("import_jobs", sa.Column("records_unmatched", sa.Integer, nullable=True))


def downgrade() -> None:
    # import_jobs counters
    op.drop_column("import_jobs", "records_unmatched")
    op.drop_column("import_jobs", "records_skipped")

    # elections.creation_method
    op.drop_index("idx_elections_creation_method", table_name="elections")
    op.drop_column("elections", "creation_method")

    # voter_history table and indexes
    op.drop_index("idx_voter_history_date_type", table_name="voter_history")
    op.drop_index("idx_voter_history_import_job_id", table_name="voter_history")
    op.drop_index("idx_voter_history_county", table_name="voter_history")
    op.drop_index("idx_voter_history_election_type", table_name="voter_history")
    op.drop_index("idx_voter_history_election_date", table_name="voter_history")
    op.drop_index("idx_voter_history_reg_num", table_name="voter_history")
    op.drop_table("voter_history")
