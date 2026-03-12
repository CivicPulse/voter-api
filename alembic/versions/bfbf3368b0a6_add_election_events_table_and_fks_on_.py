"""add election_events table and FKs on elections and voter_history

Revision ID: bfbf3368b0a6
Revises: c024a4a64e34
Create Date: 2026-03-12 14:19:47.369604
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bfbf3368b0a6"
down_revision: str | None = "c024a4a64e34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the election_events table
    op.create_table(
        "election_events",
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_name", sa.String(length=500), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_date", "event_type", name="uq_election_event_date_type"),
    )

    # Add election_event_id FK to elections
    op.add_column("elections", sa.Column("election_event_id", sa.UUID(), nullable=True))
    op.create_index("idx_elections_election_event_id", "elections", ["election_event_id"], unique=False)
    op.create_foreign_key(
        "fk_elections_election_event_id",
        "elections",
        "election_events",
        ["election_event_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add election_event_id FK to voter_history
    op.add_column("voter_history", sa.Column("election_event_id", sa.UUID(), nullable=True))
    op.create_index("idx_voter_history_election_event_id", "voter_history", ["election_event_id"], unique=False)
    op.create_foreign_key(
        "fk_voter_history_election_event_id",
        "voter_history",
        "election_events",
        ["election_event_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop voter_history FK
    op.drop_constraint("fk_voter_history_election_event_id", "voter_history", type_="foreignkey")
    op.drop_index("idx_voter_history_election_event_id", table_name="voter_history")
    op.drop_column("voter_history", "election_event_id")

    # Drop elections FK
    op.drop_constraint("fk_elections_election_event_id", "elections", type_="foreignkey")
    op.drop_index("idx_elections_election_event_id", table_name="elections")
    op.drop_column("elections", "election_event_id")

    # Drop election_events table
    op.drop_table("election_events")
