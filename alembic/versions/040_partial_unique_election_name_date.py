"""Convert uq_election_name_date to a partial unique index excluding soft-deleted rows.

Replaces the full unique constraint on (name, election_date) with a partial
unique index that only enforces uniqueness when deleted_at IS NULL. This allows
re-creating an election with the same name and date after soft-deleting the
previous one.

Revision ID: 040
Revises: 039
Create Date: 2026-02-26
"""

import sqlalchemy as sa
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_election_name_date", "elections", type_="unique")
    op.create_index(
        "uq_election_name_date",
        "elections",
        ["name", "election_date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_election_name_date", table_name="elections")
    # Before restoring the full unique constraint, remove any soft-deleted rows whose
    # (name, election_date) duplicates an active row.  Without this step, the
    # CREATE UNIQUE CONSTRAINT would fail if a name+date pair was reused after a
    # soft-delete (which is precisely what revision 040 was designed to allow).
    op.execute(
        sa.text(
            """
            DELETE FROM elections
            WHERE deleted_at IS NOT NULL
              AND (name, election_date) IN (
                  SELECT name, election_date FROM elections WHERE deleted_at IS NULL
              )
            """
        )
    )
    op.create_unique_constraint("uq_election_name_date", "elections", ["name", "election_date"])
