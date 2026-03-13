"""add eligible_county and eligible_municipality to elections

Revision ID: d1f2b72fddbe
Revises: 5cf02ee79df7
Create Date: 2026-03-12 15:42:06.054600
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f2b72fddbe"
down_revision: str | None = "5cf02ee79df7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("elections", sa.Column("eligible_county", sa.String(length=100), nullable=True))
    op.add_column("elections", sa.Column("eligible_municipality", sa.String(length=100), nullable=True))
    op.create_index("idx_elections_eligible_county", "elections", ["eligible_county"], unique=False)
    op.create_index("idx_elections_eligible_municipality", "elections", ["eligible_municipality"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_elections_eligible_municipality", table_name="elections")
    op.drop_index("idx_elections_eligible_county", table_name="elections")
    op.drop_column("elections", "eligible_municipality")
    op.drop_column("elections", "eligible_county")
