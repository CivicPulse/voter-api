"""Add foreign key constraint from geocoded_locations.voter_id to voters.id.

Revision ID: 008
Revises: 007
Create Date: 2026-02-12
"""

from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_geocoded_locations_voter_id",
        "geocoded_locations",
        "voters",
        ["voter_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_geocoded_locations_voter_id",
        "geocoded_locations",
        type_="foreignkey",
    )
