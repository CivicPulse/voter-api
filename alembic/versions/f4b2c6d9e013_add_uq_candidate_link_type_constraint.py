"""add unique constraint on candidate_links(candidate_id, link_type)

Revision ID: f4b2c6d9e013
Revises: e3a1b5c8d902
Create Date: 2026-03-15 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b2c6d9e013"
down_revision: str | None = "e3a1b5c8d902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add unique constraint on (candidate_id, link_type).

    Before adding the constraint, remove any duplicate rows so the
    constraint can be created cleanly. For each (candidate_id, link_type)
    group, keep the row with the latest created_at timestamp.
    """
    # Remove duplicates: keep the newest row per (candidate_id, link_type)
    op.execute(
        """
        DELETE FROM candidate_links
        WHERE id NOT IN (
            SELECT DISTINCT ON (candidate_id, link_type) id
            FROM candidate_links
            ORDER BY candidate_id, link_type, created_at DESC
        )
        """
    )

    op.create_unique_constraint(
        "uq_candidate_link_type",
        "candidate_links",
        ["candidate_id", "link_type"],
    )


def downgrade() -> None:
    """Remove the unique constraint."""
    op.drop_constraint("uq_candidate_link_type", "candidate_links", type_="unique")
