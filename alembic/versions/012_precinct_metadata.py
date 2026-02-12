"""Create precinct_metadata table and populate boundaries.county for precincts.

Revision ID: 012
Revises: 011
Create Date: 2026-02-12
"""

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create precinct_metadata table
    op.create_table(
        "precinct_metadata",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "boundary_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boundaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sos_district_id", sa.String(10), nullable=False),
        sa.Column("sos_id", sa.String(10), nullable=True),
        sa.Column("fips", sa.String(5), nullable=False),
        sa.Column("fips_county", sa.String(3), nullable=False),
        sa.Column("county_name", sa.String(100), nullable=False),
        sa.Column("county_number", sa.String(5), nullable=True),
        sa.Column("precinct_id", sa.String(20), nullable=False),
        sa.Column("precinct_name", sa.String(200), nullable=False),
        sa.Column("area", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("boundary_id", name="uq_precinct_metadata_boundary"),
    )
    op.create_index("ix_precinct_metadata_county_name", "precinct_metadata", ["county_name"])
    op.create_index("ix_precinct_metadata_fips", "precinct_metadata", ["fips"])
    op.create_index("ix_precinct_metadata_sos_district_id", "precinct_metadata", ["sos_district_id"])

    # Backfill boundaries.county for existing county_precinct records
    op.execute(
        """
        UPDATE boundaries
        SET county = properties->>'CTYNAME'
        WHERE boundary_type = 'county_precinct'
          AND county IS NULL
          AND properties ? 'CTYNAME'
        """
    )


def downgrade() -> None:
    # Revert county column for county_precinct records
    op.execute(
        """
        UPDATE boundaries
        SET county = NULL
        WHERE boundary_type = 'county_precinct'
        """
    )

    op.drop_index("ix_precinct_metadata_sos_district_id", table_name="precinct_metadata")
    op.drop_index("ix_precinct_metadata_fips", table_name="precinct_metadata")
    op.drop_index("ix_precinct_metadata_county_name", table_name="precinct_metadata")
    op.drop_table("precinct_metadata")
