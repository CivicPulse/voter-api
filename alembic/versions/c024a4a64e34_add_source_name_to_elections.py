"""add source_name to elections

Revision ID: c024a4a64e34
Revises: 788bdac9150d
Create Date: 2026-03-12 14:19:23.984723
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c024a4a64e34"
down_revision: str | None = "788bdac9150d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("elections", sa.Column("source_name", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("elections", "source_name")
