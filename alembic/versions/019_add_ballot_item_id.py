"""add ballot_item_id to elections for multi-race SOS feed support

Revision ID: 019
Revises: 018
Create Date: 2026-02-16

Adds ballot_item_id column to elections table so each Election record
can target a specific race within a multi-race SOS feed. When NULL,
the ingester defaults to ballotItems[0] for backward compatibility.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("elections", sa.Column("ballot_item_id", sa.String(50), nullable=True))
    op.create_index("idx_elections_ballot_item_id", "elections", ["ballot_item_id"])
    op.create_index(
        "uq_election_feed_ballot_item",
        "elections",
        ["data_source_url", "ballot_item_id"],
        unique=True,
        postgresql_where=sa.text("ballot_item_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_election_feed_ballot_item", table_name="elections")
    op.drop_index("idx_elections_ballot_item_id", table_name="elections")
    op.drop_column("elections", "ballot_item_id")
