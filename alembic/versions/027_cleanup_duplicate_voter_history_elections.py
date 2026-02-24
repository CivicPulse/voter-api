"""Delete all elections auto-created by voter history import.

Revision ID: 027
Revises: 026
Create Date: 2026-02-24

The voter history import previously auto-created election records for each
unique (date, type) combo found in the CSV. These elections are problematic:
they have generic names, no results, no details, and conflate distinct
elections that share the same date and type across different districts/counties.

This migration deletes ALL voter_history-created elections. It is safe because
voter_history records are NOT foreign-keyed to elections — they join at
query time via (election_date, normalized_election_type). The elections
table FK cascades (election_results, election_county_results) exist but
voter_history-created elections should not have result data.
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Delete all elections with creation_method='voter_history'."""
    op.execute("DELETE FROM elections WHERE creation_method = 'voter_history'")


def downgrade() -> None:
    """Downgrade is not supported — deleted elections cannot be recovered."""
    raise NotImplementedError("Cannot restore deleted elections. Restore from a database backup if needed.")
