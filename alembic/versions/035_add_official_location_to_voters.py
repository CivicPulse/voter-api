"""add official location to voters

Add official_latitude, official_longitude, official_point, official_source,
and official_is_override columns to the voters table.  Backfill from the
current is_primary=true geocoded location for each voter.

Revision ID: 035
Revises: 034
Create Date: 2026-02-25
"""

from collections.abc import Sequence

import geoalchemy2  # noqa: F401 — registers Geometry type with Alembic
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035"
down_revision: str | None = "034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add columns
    op.add_column("voters", sa.Column("official_latitude", sa.Double(), nullable=True))
    op.add_column("voters", sa.Column("official_longitude", sa.Double(), nullable=True))
    op.add_column(
        "voters",
        sa.Column(
            "official_point",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT"),
            nullable=True,
        ),
    )
    op.add_column("voters", sa.Column("official_source", sa.String(50), nullable=True))
    op.add_column(
        "voters",
        sa.Column("official_is_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # GiST index for spatial queries on official_point
    op.create_index("ix_voters_official_point", "voters", ["official_point"], postgresql_using="gist")

    # Backfill from current is_primary=true geocoded locations
    op.execute(
        """
        UPDATE voters v
        SET official_latitude = gl.latitude,
            official_longitude = gl.longitude,
            official_point = gl.point,
            official_source = gl.source_type,
            official_is_override = false
        FROM geocoded_locations gl
        WHERE gl.voter_id = v.id AND gl.is_primary = true
        """
    )


def downgrade() -> None:
    op.drop_index("ix_voters_official_point", table_name="voters", postgresql_using="gist")
    op.drop_column("voters", "official_is_override")
    op.drop_column("voters", "official_source")
    op.drop_column("voters", "official_point")
    op.drop_column("voters", "official_longitude")
    op.drop_column("voters", "official_latitude")
