"""Create boundaries table.

Revision ID: 004
Revises: 003
Create Date: 2026-02-11
"""

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boundaries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("boundary_type", sa.String(50), nullable=False),
        sa.Column("boundary_identifier", sa.String(50), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("county", sa.String(100), nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=4326,
                from_text="ST_GeomFromEWKT",
            ),
            nullable=False,
        ),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("properties", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("boundary_type", "boundary_identifier", "county", name="uq_boundary_type_id_county"),
    )
    op.create_index("ix_boundaries_boundary_type", "boundaries", ["boundary_type"])
    op.create_index("ix_boundaries_county", "boundaries", ["county"])


def downgrade() -> None:
    op.drop_index("ix_boundaries_county", table_name="boundaries")
    op.drop_index("ix_boundaries_boundary_type", table_name="boundaries")
    op.drop_table("boundaries")
