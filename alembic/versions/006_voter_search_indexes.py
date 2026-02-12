"""Add composite search indexes for voter query performance.

Revision ID: 006
Revises: 005
Create Date: 2026-02-11
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add composite indexes for common voter search patterns."""
    # County + status for filtered searches
    op.create_index("ix_voters_county_status", "voters", ["county", "status"])

    # County + precinct for precinct-level queries
    op.create_index("ix_voters_county_precinct_combo", "voters", ["county", "county_precinct"])

    # Status + present_in_latest_import for active voter filtering
    op.create_index(
        "ix_voters_status_present",
        "voters",
        ["status", "present_in_latest_import"],
    )

    # Residence city + zipcode for address-based searches
    op.create_index(
        "ix_voters_city_zip",
        "voters",
        ["residence_city", "residence_zipcode"],
    )


def downgrade() -> None:
    """Remove composite search indexes."""
    op.drop_index("ix_voters_city_zip")
    op.drop_index("ix_voters_status_present")
    op.drop_index("ix_voters_county_precinct_combo")
    op.drop_index("ix_voters_county_status")
