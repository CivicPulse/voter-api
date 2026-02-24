"""Cleanup duplicate elections created by voter history import.

Revision ID: 027
Revises: 026
Create Date: 2026-02-24

When voter history CSVs were imported, the auto-election-creation logic
created new elections instead of associating with existing ones when the
normalized type from the CSV (e.g., "runoff") didn't match the manually-
created election's type (e.g., "special") on the same date.

This migration deletes the auto-created duplicates. It is safe because
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
    """Delete voter_history-created elections that duplicate a manually-created one."""
    op.execute(
        """
        DELETE FROM elections e1
        WHERE e1.creation_method = 'voter_history'
          AND EXISTS (
              SELECT 1 FROM elections e2
              WHERE e2.election_date = e1.election_date
                AND e2.id != e1.id
                AND e2.creation_method != 'voter_history'
          )
        """
    )


def downgrade() -> None:
    """Downgrade is not supported — deleted elections cannot be recovered."""
    raise NotImplementedError("Cannot restore deleted duplicate elections. Restore from a database backup if needed.")
