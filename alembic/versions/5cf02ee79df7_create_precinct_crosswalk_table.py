"""create precinct_crosswalk table

Revision ID: 5cf02ee79df7
Revises: c024a4a64e34
Create Date: 2026-03-12 14:23:11.485504
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5cf02ee79df7"
down_revision: str | None = "bfbf3368b0a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "precinct_crosswalk",
        sa.Column("county_code", sa.String(length=10), nullable=False),
        sa.Column("county_name", sa.String(length=100), nullable=False),
        sa.Column("voter_precinct_code", sa.String(length=50), nullable=False),
        sa.Column("boundary_precinct_identifier", sa.String(length=100), nullable=False),
        sa.Column("source", sa.String(length=50), server_default="spatial_join", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("county_name", "voter_precinct_code", name="uq_precinct_crosswalk_county_precinct"),
    )


def downgrade() -> None:
    op.drop_table("precinct_crosswalk")
