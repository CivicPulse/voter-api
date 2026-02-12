"""Add voters and import_jobs tables.

Revision ID: 002
Revises: 001
Create Date: 2026-02-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create import_jobs table
    op.create_table(
        "import_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_records", sa.Integer, nullable=True),
        sa.Column("records_succeeded", sa.Integer, nullable=True),
        sa.Column("records_failed", sa.Integer, nullable=True),
        sa.Column("records_inserted", sa.Integer, nullable=True),
        sa.Column("records_updated", sa.Integer, nullable=True),
        sa.Column("records_soft_deleted", sa.Integer, nullable=True),
        sa.Column("error_log", JSONB, nullable=True),
        sa.Column("last_processed_offset", sa.Integer, nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_import_status", "import_jobs", ["status"])
    op.create_index("ix_import_file_type", "import_jobs", ["file_type"])
    op.create_index("ix_import_created_at", "import_jobs", ["created_at"])

    # Create voters table
    op.create_table(
        "voters",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("county", sa.String(100), nullable=False),
        sa.Column("voter_registration_number", sa.String(20), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("status_reason", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("suffix", sa.String(20), nullable=True),
        sa.Column("birth_year", sa.Integer, nullable=True),
        sa.Column("race", sa.String(20), nullable=True),
        sa.Column("gender", sa.String(10), nullable=True),
        # Residence address
        sa.Column("residence_street_number", sa.String(20), nullable=True),
        sa.Column("residence_pre_direction", sa.String(10), nullable=True),
        sa.Column("residence_street_name", sa.String(100), nullable=True),
        sa.Column("residence_street_type", sa.String(20), nullable=True),
        sa.Column("residence_post_direction", sa.String(10), nullable=True),
        sa.Column("residence_apt_unit_number", sa.String(20), nullable=True),
        sa.Column("residence_city", sa.String(100), nullable=True),
        sa.Column("residence_zipcode", sa.String(10), nullable=True),
        # Mailing address
        sa.Column("mailing_street_number", sa.String(20), nullable=True),
        sa.Column("mailing_street_name", sa.String(100), nullable=True),
        sa.Column("mailing_apt_unit_number", sa.String(20), nullable=True),
        sa.Column("mailing_city", sa.String(100), nullable=True),
        sa.Column("mailing_zipcode", sa.String(10), nullable=True),
        sa.Column("mailing_state", sa.String(50), nullable=True),
        sa.Column("mailing_country", sa.String(50), nullable=True),
        # Registered districts
        sa.Column("county_precinct", sa.String(20), nullable=True),
        sa.Column("county_precinct_description", sa.String(200), nullable=True),
        sa.Column("municipal_precinct", sa.String(20), nullable=True),
        sa.Column("municipal_precinct_description", sa.String(200), nullable=True),
        sa.Column("congressional_district", sa.String(10), nullable=True),
        sa.Column("state_senate_district", sa.String(10), nullable=True),
        sa.Column("state_house_district", sa.String(10), nullable=True),
        sa.Column("judicial_district", sa.String(10), nullable=True),
        sa.Column("county_commission_district", sa.String(10), nullable=True),
        sa.Column("school_board_district", sa.String(10), nullable=True),
        sa.Column("city_council_district", sa.String(10), nullable=True),
        sa.Column("municipal_school_board_district", sa.String(10), nullable=True),
        sa.Column("water_board_district", sa.String(10), nullable=True),
        sa.Column("super_council_district", sa.String(10), nullable=True),
        sa.Column("super_commissioner_district", sa.String(10), nullable=True),
        sa.Column("super_school_board_district", sa.String(10), nullable=True),
        sa.Column("fire_district", sa.String(10), nullable=True),
        sa.Column("municipality", sa.String(100), nullable=True),
        sa.Column("combo", sa.String(20), nullable=True),
        sa.Column("land_lot", sa.String(20), nullable=True),
        sa.Column("land_district", sa.String(20), nullable=True),
        # Dates
        sa.Column("registration_date", sa.Date, nullable=True),
        sa.Column("last_modified_date", sa.Date, nullable=True),
        sa.Column("date_of_last_contact", sa.Date, nullable=True),
        sa.Column("last_vote_date", sa.Date, nullable=True),
        sa.Column("voter_created_date", sa.Date, nullable=True),
        sa.Column("last_party_voted", sa.String(20), nullable=True),
        # Soft-delete tracking
        sa.Column("present_in_latest_import", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Import tracking
        sa.Column("last_seen_in_import_id", UUID(as_uuid=True), nullable=True),
        sa.Column("first_seen_in_import_id", UUID(as_uuid=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Create indexes
    op.create_index("ix_voters_county", "voters", ["county"])
    op.create_index("ix_voters_registration_number", "voters", ["voter_registration_number"], unique=True)
    op.create_index("ix_voters_last_name", "voters", ["last_name"])
    op.create_index("ix_voters_first_name", "voters", ["first_name"])
    op.create_index("ix_voters_residence_zipcode", "voters", ["residence_zipcode"])
    op.create_index("ix_voters_status", "voters", ["status"])
    op.create_index("ix_voters_county_precinct", "voters", ["county_precinct"])
    op.create_index("ix_voters_congressional_district", "voters", ["congressional_district"])
    op.create_index("ix_voters_present_in_latest", "voters", ["present_in_latest_import"])
    op.create_index("ix_voters_name_search", "voters", ["last_name", "first_name"])


def downgrade() -> None:
    op.drop_table("voters")
    op.drop_table("import_jobs")
