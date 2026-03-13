"""Add candidate import fields for GA SoS bulk import.

Adds columns to the candidates table for storing data from GA Secretary of
State candidate qualifying lists: contest_name, qualified_date, occupation,
email, home_county, municipality, and import_job_id (FK to import_jobs).

Revision ID: 041
Revises: 040
Create Date: 2026-03-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add import-related columns and index to the candidates table."""
    op.add_column("candidates", sa.Column("contest_name", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("qualified_date", sa.Date(), nullable=True))
    op.add_column("candidates", sa.Column("occupation", sa.String(200), nullable=True))
    op.add_column("candidates", sa.Column("email", sa.String(200), nullable=True))
    op.add_column("candidates", sa.Column("home_county", sa.String(100), nullable=True))
    op.add_column("candidates", sa.Column("municipality", sa.String(100), nullable=True))
    op.add_column(
        "candidates",
        sa.Column(
            "import_job_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_candidates_import_job_id",
        "candidates",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_candidates_home_county", "candidates", ["home_county"])


def downgrade() -> None:
    """Remove import-related columns and index from the candidates table."""
    op.drop_index("ix_candidates_home_county", table_name="candidates")
    op.drop_constraint("fk_candidates_import_job_id", "candidates", type_="foreignkey")
    op.drop_column("candidates", "import_job_id")
    op.drop_column("candidates", "municipality")
    op.drop_column("candidates", "home_county")
    op.drop_column("candidates", "email")
    op.drop_column("candidates", "occupation")
    op.drop_column("candidates", "qualified_date")
    op.drop_column("candidates", "contest_name")
