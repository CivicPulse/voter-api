"""add records_needs_review to import_jobs

Revision ID: 788bdac9150d
Revises: 3923230c8573
Create Date: 2026-03-12 00:03:05.578629
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "788bdac9150d"
down_revision: str | None = "3923230c8573"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("records_needs_review", sa.Integer(), server_default=sa.text("0"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("import_jobs", "records_needs_review")
