"""add composite index on precinct_metadata for county+sos_id lookups

Revision ID: 018
Revises: 017
Create Date: 2026-02-16

Adds a composite index on precinct_metadata(county_name, sos_id)
to support multi-strategy precinct matching via SOS ID fallback.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_precinct_metadata_county_sos_id",
        "precinct_metadata",
        ["county_name", "sos_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_precinct_metadata_county_sos_id", table_name="precinct_metadata")
