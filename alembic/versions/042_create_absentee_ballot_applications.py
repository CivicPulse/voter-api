"""Create absentee_ballot_applications table.

Stores GA Secretary of State absentee ballot application and return data.
Each row represents one absentee ballot application for a voter in a
specific election/ballot style.

Revision ID: 042
Revises: 041
Create Date: 2026-03-11
"""

import sqlalchemy as sa
from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the absentee_ballot_applications table with indexes."""
    op.create_table(
        "absentee_ballot_applications",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        # Voter identification
        sa.Column("county", sa.String(100), nullable=False),
        sa.Column("voter_registration_number", sa.String(20), nullable=False),
        # Name fields
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("suffix", sa.String(20), nullable=True),
        # Residence address
        sa.Column("street_number", sa.String(20), nullable=True),
        sa.Column("street_name", sa.String(200), nullable=True),
        sa.Column("apt_unit", sa.String(50), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("zip_code", sa.String(20), nullable=True),
        # Mailing address
        sa.Column("mailing_street_number", sa.String(20), nullable=True),
        sa.Column("mailing_street_name", sa.String(200), nullable=True),
        sa.Column("mailing_apt_unit", sa.String(50), nullable=True),
        sa.Column("mailing_city", sa.String(100), nullable=True),
        sa.Column("mailing_state", sa.String(2), nullable=True),
        sa.Column("mailing_zip_code", sa.String(20), nullable=True),
        # Status fields
        sa.Column("application_status", sa.String(50), nullable=True),
        sa.Column("ballot_status", sa.String(50), nullable=True),
        sa.Column("status_reason", sa.String(200), nullable=True),
        # Date fields
        sa.Column("application_date", sa.Date(), nullable=True),
        sa.Column("ballot_issued_date", sa.Date(), nullable=True),
        sa.Column("ballot_return_date", sa.Date(), nullable=True),
        # Ballot details
        sa.Column("ballot_style", sa.String(50), nullable=True),
        sa.Column("ballot_assisted", sa.Boolean(), nullable=True),
        sa.Column("challenged_provisional", sa.Boolean(), nullable=True),
        sa.Column("id_required", sa.Boolean(), nullable=True),
        # Precinct / district fields
        sa.Column("municipal_precinct", sa.String(20), nullable=True),
        sa.Column("county_precinct", sa.String(20), nullable=True),
        sa.Column("congressional_district", sa.String(10), nullable=True),
        sa.Column("state_senate_district", sa.String(10), nullable=True),
        sa.Column("state_house_district", sa.String(10), nullable=True),
        sa.Column("judicial_district", sa.String(10), nullable=True),
        sa.Column("combo", sa.String(20), nullable=True),
        sa.Column("vote_center_id", sa.String(50), nullable=True),
        sa.Column("ballot_id", sa.String(50), nullable=True),
        sa.Column("party", sa.String(50), nullable=True),
        # Import tracking
        sa.Column(
            "import_job_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.UniqueConstraint(
            "voter_registration_number",
            "application_date",
            "ballot_style",
            name="uq_aba_voter_appdate_ballotstyle",
        ),
    )

    # Indexes
    op.create_index("ix_aba_voter_reg_num", "absentee_ballot_applications", ["voter_registration_number"])
    op.create_index("ix_aba_county", "absentee_ballot_applications", ["county"])
    op.create_index("ix_aba_application_status", "absentee_ballot_applications", ["application_status"])
    op.create_index("ix_aba_ballot_status", "absentee_ballot_applications", ["ballot_status"])
    op.create_index("ix_aba_import_job_id", "absentee_ballot_applications", ["import_job_id"])


def downgrade() -> None:
    """Drop the absentee_ballot_applications table."""
    op.drop_index("ix_aba_import_job_id", table_name="absentee_ballot_applications")
    op.drop_index("ix_aba_ballot_status", table_name="absentee_ballot_applications")
    op.drop_index("ix_aba_application_status", table_name="absentee_ballot_applications")
    op.drop_index("ix_aba_county", table_name="absentee_ballot_applications")
    op.drop_index("ix_aba_voter_reg_num", table_name="absentee_ballot_applications")
    op.drop_table("absentee_ballot_applications")
