"""Create county_metadata table for Census TIGER/Line county attributes.

Revision ID: 011
Revises: 010
Create Date: 2026-02-12
"""

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "county_metadata",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("geoid", sa.String(5), nullable=False),
        sa.Column("fips_state", sa.String(2), nullable=False),
        sa.Column("fips_county", sa.String(3), nullable=False),
        sa.Column("gnis_code", sa.String(8), nullable=True),
        sa.Column("geoid_fq", sa.String(20), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_lsad", sa.String(200), nullable=False),
        sa.Column("lsad_code", sa.String(2), nullable=True),
        sa.Column("class_fp", sa.String(2), nullable=True),
        sa.Column("mtfcc", sa.String(5), nullable=True),
        sa.Column("csa_code", sa.String(3), nullable=True),
        sa.Column("cbsa_code", sa.String(5), nullable=True),
        sa.Column("metdiv_code", sa.String(5), nullable=True),
        sa.Column("functional_status", sa.String(1), nullable=True),
        sa.Column("land_area_m2", sa.BigInteger, nullable=True),
        sa.Column("water_area_m2", sa.BigInteger, nullable=True),
        sa.Column("internal_point_lat", sa.String(15), nullable=True),
        sa.Column("internal_point_lon", sa.String(15), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("geoid", name="uq_county_metadata_geoid"),
    )
    op.create_index("ix_county_metadata_name", "county_metadata", ["name"])
    op.create_index("ix_county_metadata_fips_state", "county_metadata", ["fips_state"])


def downgrade() -> None:
    op.drop_index("ix_county_metadata_fips_state", table_name="county_metadata")
    op.drop_index("ix_county_metadata_name", table_name="county_metadata")
    op.drop_table("county_metadata")
