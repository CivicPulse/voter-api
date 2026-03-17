"""Add GIN index on analysis_results.mismatch_details for JSONB containment queries.

Revision ID: 030_gin_mismatch_details
Revises: f4b2c6d9e013
Create Date: 2026-03-16
"""

from alembic import op

# revision identifiers
revision = "030_gin_mismatch_details"
down_revision = "f4b2c6d9e013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_result_mismatch_details_gin",
        "analysis_results",
        ["mismatch_details"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_result_mismatch_details_gin", table_name="analysis_results")
