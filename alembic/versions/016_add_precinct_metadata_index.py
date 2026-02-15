"""add composite index on precinct_metadata for county+precinct lookups

Revision ID: 016
Revises: 015
Create Date: 2026-02-14

Adds a composite index on precinct_metadata(county_name, precinct_id)
to accelerate per-county precinct lookups in the precinct GeoJSON endpoint.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers
revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_precinct_metadata_county_precinct_id",
        "precinct_metadata",
        ["county_name", "precinct_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_precinct_metadata_county_precinct_id", table_name="precinct_metadata")
