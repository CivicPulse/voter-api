"""Create analysis_runs and analysis_results tables.

Revision ID: 005
Revises: 004
Create Date: 2026-02-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create analysis_runs and analysis_results tables."""
    op.create_table(
        "analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total_voters_analyzed", sa.Integer(), nullable=True),
        sa.Column("match_count", sa.Integer(), nullable=True),
        sa.Column("mismatch_count", sa.Integer(), nullable=True),
        sa.Column("unable_to_analyze_count", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_processed_voter_offset", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_run_status", "analysis_runs", ["status"])
    op.create_index("ix_analysis_run_created_at", "analysis_runs", ["created_at"])

    op.create_table(
        "analysis_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("determined_boundaries", postgresql.JSONB(), nullable=False),
        sa.Column("registered_boundaries", postgresql.JSONB(), nullable=False),
        sa.Column("match_status", sa.String(30), nullable=False),
        sa.Column("mismatch_details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["voter_id"], ["voters.id"]),
        sa.UniqueConstraint("analysis_run_id", "voter_id", name="ix_result_run_voter"),
    )
    op.create_index("ix_result_run_id", "analysis_results", ["analysis_run_id"])
    op.create_index("ix_result_voter_id", "analysis_results", ["voter_id"])
    op.create_index("ix_result_match_status", "analysis_results", ["match_status"])


def downgrade() -> None:
    """Drop analysis_results and analysis_runs tables."""
    op.drop_table("analysis_results")
    op.drop_table("analysis_runs")
