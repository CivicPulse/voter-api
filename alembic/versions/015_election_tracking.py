"""add election tracking tables

Revision ID: 015
Revises: 014
Create Date: 2026-02-14

Creates elections, election_results, and election_county_results tables
with indexes and constraints per data-model.md.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- elections ---
    op.create_table(
        "elections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("election_date", sa.Date, nullable=False),
        sa.Column("election_type", sa.String(50), nullable=False),
        sa.Column("district", sa.String(200), nullable=False),
        sa.Column("data_source_url", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_interval_seconds", sa.Integer, nullable=False, server_default="120"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "election_date", name="uq_election_name_date"),
        sa.CheckConstraint("status IN ('active', 'finalized')", name="ck_election_status"),
        sa.CheckConstraint("refresh_interval_seconds >= 60", name="ck_election_refresh_interval"),
    )
    op.create_index("idx_elections_status", "elections", ["status"])
    op.create_index("idx_elections_election_date", "elections", ["election_date"])

    # --- election_results ---
    op.create_table(
        "election_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "election_id",
            UUID(as_uuid=True),
            sa.ForeignKey("elections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("precincts_participating", sa.Integer, nullable=True),
        sa.Column("precincts_reporting", sa.Integer, nullable=True),
        sa.Column("results_data", JSONB, nullable=False),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("election_id", name="uq_election_results_election_id"),
    )
    op.create_index(
        "idx_election_results_jsonb",
        "election_results",
        ["results_data"],
        postgresql_using="gin",
    )

    # --- election_county_results ---
    op.create_table(
        "election_county_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "election_id",
            UUID(as_uuid=True),
            sa.ForeignKey("elections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("county_name", sa.String(100), nullable=False),
        sa.Column("county_name_normalized", sa.String(100), nullable=False),
        sa.Column("precincts_participating", sa.Integer, nullable=True),
        sa.Column("precincts_reporting", sa.Integer, nullable=True),
        sa.Column("results_data", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("election_id", "county_name", name="uq_election_county_results"),
    )
    op.create_index("idx_election_county_results_election_id", "election_county_results", ["election_id"])
    op.create_index(
        "idx_election_county_results_county_normalized",
        "election_county_results",
        ["county_name_normalized"],
    )
    op.create_index(
        "idx_election_county_results_jsonb",
        "election_county_results",
        ["results_data"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("election_county_results")
    op.drop_table("election_results")
    op.drop_table("elections")
