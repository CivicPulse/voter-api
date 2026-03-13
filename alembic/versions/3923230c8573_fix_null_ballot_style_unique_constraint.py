"""Fix NULL ballot_style unique constraint with COALESCE

PostgreSQL treats NULLs as distinct in UNIQUE constraints, causing duplicate
rows on re-import when ballot_style is NULL.  Replace the plain
UniqueConstraint with a unique index that uses COALESCE(ballot_style, '').

WARNING: The upgrade step deletes duplicate rows (keeping only the first by id)
where (voter_registration_number, application_date, COALESCE(ballot_style, ''))
would collide under the new index.  This is a **data-destructive** migration.

Revision ID: 3923230c8573
Revises: a7ce7a38cece
Create Date: 2026-03-11
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3923230c8573"
down_revision: str | None = "a7ce7a38cece"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_aba_voter_appdate_ballotstyle",
        "absentee_ballot_applications",
        type_="unique",
    )
    # Remove duplicates that the new COALESCE index would reject.
    # NULL ballot_style values that were previously distinct become
    # collisions once COALESCE(ballot_style, '') maps them to ''.
    op.execute(
        """
        DELETE FROM absentee_ballot_applications
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY voter_registration_number, application_date, COALESCE(ballot_style, '')
                        ORDER BY id
                    ) AS rn
                FROM absentee_ballot_applications
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_aba_voter_appdate_ballotstyle "
        "ON absentee_ballot_applications ("
        "    voter_registration_number, application_date, COALESCE(ballot_style, '')"
        ")"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_aba_voter_appdate_ballotstyle")
    op.create_unique_constraint(
        "uq_aba_voter_appdate_ballotstyle",
        "absentee_ballot_applications",
        ["voter_registration_number", "application_date", "ballot_style"],
    )
