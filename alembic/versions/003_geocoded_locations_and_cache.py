"""Create geocoded_locations, geocoder_cache, and geocoding_jobs tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-11
"""

import geoalchemy2  # noqa: F401
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Geocoded locations
    op.create_table(
        "geocoded_locations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voter_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column(
            "point",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=4326, from_text="ST_GeomFromEWKT"),
            nullable=False,
        ),
        sa.Column("confidence_score", sa.Double(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("input_address", sa.String(), nullable=True),
        sa.Column(
            "geocoded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("voter_id", "source_type", name="uq_voter_source"),
    )
    op.create_index("ix_geocoded_locations_voter_id", "geocoded_locations", ["voter_id"])
    op.create_index(
        "ix_geocoded_primary",
        "geocoded_locations",
        ["voter_id"],
        postgresql_where=sa.text("is_primary = true"),
    )

    # Geocoder cache
    op.create_table(
        "geocoder_cache",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("normalized_address", sa.String(), nullable=False),
        sa.Column("latitude", sa.Double(), nullable=False),
        sa.Column("longitude", sa.Double(), nullable=False),
        sa.Column("confidence_score", sa.Double(), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(), nullable=True),
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "normalized_address", name="uq_provider_address"),
    )

    # Geocoding jobs
    op.create_table(
        "geocoding_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("county", sa.String(100), nullable=True),
        sa.Column("force_regeocode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("total_records", sa.Integer(), nullable=True),
        sa.Column("processed", sa.Integer(), nullable=True),
        sa.Column("succeeded", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("cache_hits", sa.Integer(), nullable=True),
        sa.Column("last_processed_voter_offset", sa.Integer(), nullable=True),
        sa.Column("error_log", postgresql.JSONB(), nullable=True),
        sa.Column("triggered_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_geocoding_jobs_status", "geocoding_jobs", ["status"])
    op.create_index("ix_geocoding_jobs_created_at", "geocoding_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("geocoding_jobs")
    op.drop_table("geocoder_cache")
    op.drop_index("ix_geocoded_primary", table_name="geocoded_locations")
    op.drop_index("ix_geocoded_locations_voter_id", table_name="geocoded_locations")
    op.drop_table("geocoded_locations")
