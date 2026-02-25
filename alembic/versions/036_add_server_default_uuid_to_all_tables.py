"""Add server_default gen_random_uuid() to all UUID id columns missing it.

Core-level INSERT operations (e.g., pg_insert()) bypass ORM defaults, so
tables without a server_default on the id column fail with NOT NULL violations.
This migration adds the server_default to all tables that are missing it.

Revision ID: 036
Revises: 035
Create Date: 2026-02-25
"""

import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

# Tables that already have gen_random_uuid() as server_default:
# elections, election_results, election_county_results, voter_history
_TABLES_NEEDING_DEFAULT = [
    "addresses",
    "agenda_items",
    "analysis_results",
    "analysis_runs",
    "audit_logs",
    "boundaries",
    "county_districts",
    "county_metadata",
    "elected_official_sources",
    "elected_officials",
    "export_jobs",
    "geocoded_locations",
    "geocoder_cache",
    "geocoding_jobs",
    "governing_bodies",
    "governing_body_types",
    "import_jobs",
    "meeting_attachments",
    "meeting_video_embeds",
    "meetings",
    "passkeys",
    "password_reset_tokens",
    "precinct_metadata",
    "totp_credentials",
    "totp_recovery_codes",
    "user_invites",
    "users",
    "voters",
]


def upgrade() -> None:
    for table in _TABLES_NEEDING_DEFAULT:
        op.alter_column(
            table,
            "id",
            server_default=sa.text("gen_random_uuid()"),
        )


def downgrade() -> None:
    for table in _TABLES_NEEDING_DEFAULT:
        op.alter_column(
            table,
            "id",
            server_default=None,
        )
