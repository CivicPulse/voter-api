"""Add foreign key constraints on analysis_results for analysis_run_id and voter_id.

Revision ID: 009
Revises: 008
Create Date: 2026-02-12
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_analysis_results_analysis_run_id",
        "analysis_results",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_analysis_results_voter_id",
        "analysis_results",
        "voters",
        ["voter_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_analysis_results_voter_id",
        "analysis_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_analysis_results_analysis_run_id",
        "analysis_results",
        type_="foreignkey",
    )
