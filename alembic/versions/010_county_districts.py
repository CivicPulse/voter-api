"""Create county_districts table for county-to-district mappings.

Revision ID: 010
Revises: 009
Create Date: 2026-02-12
"""

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "county_districts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("county_name", sa.String(100), nullable=False),
        sa.Column("boundary_type", sa.String(50), nullable=False),
        sa.Column("district_identifier", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("county_name", "boundary_type", "district_identifier", name="uq_county_district"),
    )
    op.create_index("ix_county_districts_county_name", "county_districts", ["county_name"])
    op.create_index(
        "ix_county_districts_type_identifier",
        "county_districts",
        ["boundary_type", "district_identifier"],
    )


def downgrade() -> None:
    op.drop_index("ix_county_districts_type_identifier", table_name="county_districts")
    op.drop_index("ix_county_districts_county_name", table_name="county_districts")
    op.drop_table("county_districts")
