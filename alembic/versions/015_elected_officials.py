"""add elected_officials and elected_official_sources tables

Revision ID: 015
Revises: 014
Create Date: 2026-02-14

Introduces two tables for elected official management:
  - elected_officials: canonical records the API serves (admin-approved or auto)
  - elected_official_sources: cached responses from external data providers
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "elected_officials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # District linkage
        sa.Column("boundary_type", sa.String(50), nullable=False, index=True),
        sa.Column("district_identifier", sa.String(50), nullable=False),
        # Person
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("party", sa.String(50), nullable=True),
        sa.Column("title", sa.String(100), nullable=True),
        sa.Column("photo_url", sa.Text, nullable=True),
        # Term / election dates
        sa.Column("term_start_date", sa.Date, nullable=True),
        sa.Column("term_end_date", sa.Date, nullable=True),
        sa.Column("last_election_date", sa.Date, nullable=True),
        sa.Column("next_election_date", sa.Date, nullable=True),
        # Contact
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("office_address", sa.Text, nullable=True),
        # External IDs (JSONB)
        sa.Column("external_ids", postgresql.JSONB, nullable=True),
        # Admin approval
        sa.Column("status", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_elected_officials_district", "elected_officials", ["boundary_type", "district_identifier"])
    op.create_index("ix_elected_officials_name", "elected_officials", ["last_name", "first_name"])
    op.create_unique_constraint(
        "uq_official_district_name", "elected_officials", ["boundary_type", "district_identifier", "full_name"]
    )
    op.create_check_constraint("ck_official_status", "elected_officials", "status IN ('auto', 'approved', 'manual')")

    op.create_table(
        "elected_official_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Link to canonical record
        sa.Column(
            "elected_official_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("elected_officials.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # Source identification
        sa.Column("source_name", sa.String(50), nullable=False, index=True),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        # District context
        sa.Column("boundary_type", sa.String(50), nullable=False),
        sa.Column("district_identifier", sa.String(50), nullable=False),
        # Raw cached response
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        # Normalized fields
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("party", sa.String(50), nullable=True),
        sa.Column("title", sa.String(100), nullable=True),
        sa.Column("photo_url", sa.Text, nullable=True),
        # Term dates
        sa.Column("term_start_date", sa.Date, nullable=True),
        sa.Column("term_end_date", sa.Date, nullable=True),
        # Contact
        sa.Column("website", sa.Text, nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("office_address", sa.Text, nullable=True),
        # Tracking
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("true")),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_source_district", "elected_official_sources", ["boundary_type", "district_identifier"])
    op.create_unique_constraint("uq_source_record", "elected_official_sources", ["source_name", "source_record_id"])


def downgrade() -> None:
    op.drop_table("elected_official_sources")
    op.drop_table("elected_officials")
