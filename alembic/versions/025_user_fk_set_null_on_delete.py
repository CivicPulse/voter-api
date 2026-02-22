"""Add ON DELETE SET NULL to nullable user FK columns.

Revision ID: 025
Revises: 024
Create Date: 2026-02-22

Updates the nullable foreign keys on meetings (submitted_by, approved_by)
and elected_officials (approved_by_id) that reference users.id so that
deleting a user sets those columns to NULL rather than raising a FK
constraint violation.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: str = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace RESTRICT FKs with ON DELETE SET NULL on user references."""
    # elected_officials.approved_by_id
    op.drop_constraint(
        "elected_officials_approved_by_id_fkey",
        "elected_officials",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "elected_officials_approved_by_id_fkey",
        "elected_officials",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # meetings.submitted_by
    op.drop_constraint(
        "meetings_submitted_by_fkey",
        "meetings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "meetings_submitted_by_fkey",
        "meetings",
        "users",
        ["submitted_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # meetings.approved_by
    op.drop_constraint(
        "meetings_approved_by_fkey",
        "meetings",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "meetings_approved_by_fkey",
        "meetings",
        "users",
        ["approved_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Revert to RESTRICT (default) behavior on user FK columns."""
    # meetings.approved_by
    op.drop_constraint("meetings_approved_by_fkey", "meetings", type_="foreignkey")
    op.create_foreign_key(
        "meetings_approved_by_fkey",
        "meetings",
        "users",
        ["approved_by"],
        ["id"],
    )

    # meetings.submitted_by
    op.drop_constraint("meetings_submitted_by_fkey", "meetings", type_="foreignkey")
    op.create_foreign_key(
        "meetings_submitted_by_fkey",
        "meetings",
        "users",
        ["submitted_by"],
        ["id"],
    )

    # elected_officials.approved_by_id
    op.drop_constraint(
        "elected_officials_approved_by_id_fkey",
        "elected_officials",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "elected_officials_approved_by_id_fkey",
        "elected_officials",
        "users",
        ["approved_by_id"],
        ["id"],
    )
