"""add matched_address column to geocoder_cache

Revision ID: 014
Revises: 013
Create Date: 2026-02-13

Adds a nullable matched_address text column to geocoder_cache so the
provider's canonical matched address is persisted alongside coordinates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("geocoder_cache", sa.Column("matched_address", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("geocoder_cache", "matched_address")
