"""Normalize voter_registration_number: strip leading zeros.

Revision ID: 030
Revises: 029
Create Date: 2026-02-24

The voter_history table stores registration numbers with leading zeros
(e.g., "00013148") from the GA SoS voter history CSV, while the voters
table stores them without (e.g., "13148"). This mismatch prevents joins
between the two tables. This migration strips leading zeros from both
tables so they use a consistent unpadded format.

Because stripping zeros can cause collisions on the unique constraint
``uq_voter_history_participation (voter_registration_number, election_date,
election_type)``, duplicate rows are deleted before the UPDATE.
"""

from alembic import op

revision: str = "030"
down_revision: str | None = "029"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Strip leading zeros from voter_registration_number in both tables."""
    # 1. Delete voter_history rows that would collide after normalization.
    #    Two rows that differ only in leading zeros (e.g., "00013148" vs "13148")
    #    would violate the unique constraint once both are normalized. Keep the
    #    row whose registration number is already shorter (fewer leading zeros).
    op.execute(
        """
        DELETE FROM voter_history vh1
        USING voter_history vh2
        WHERE vh1.voter_registration_number <> vh2.voter_registration_number
          AND LTRIM(vh1.voter_registration_number, '0') = LTRIM(vh2.voter_registration_number, '0')
          AND vh1.election_date = vh2.election_date
          AND vh1.election_type = vh2.election_type
          AND LENGTH(vh1.voter_registration_number) > LENGTH(vh2.voter_registration_number)
        """
    )

    # 2. Normalize remaining voter_history rows.
    op.execute(
        """
        UPDATE voter_history
        SET voter_registration_number = CASE
            WHEN LTRIM(voter_registration_number, '0') = '' THEN '0'
            ELSE LTRIM(voter_registration_number, '0')
        END
        WHERE voter_registration_number ~ '^0'
        """
    )

    # 3. Safety pass: normalize voters table (should already be clean, but
    #    guard against future CSV format changes).
    #    First check for collisions: if two rows differ only by leading zeros
    #    (e.g., "000123" and "123"), the unique constraint would be violated.
    #    This should not happen in practice since the voter file doesn't
    #    zero-pad, but abort with a clear error if it does.
    op.execute(
        """
        DO $$
        DECLARE
            collision_count integer;
        BEGIN
            SELECT COUNT(*) INTO collision_count
            FROM voters v1
            JOIN voters v2 ON v1.id <> v2.id
                AND v1.voter_registration_number <> v2.voter_registration_number
                AND LTRIM(v1.voter_registration_number, '0') = LTRIM(v2.voter_registration_number, '0');
            IF collision_count > 0 THEN
                RAISE EXCEPTION 'Found % voter rows that collide after normalization.', collision_count;
            END IF;
        END $$
        """
    )
    op.execute(
        """
        UPDATE voters
        SET voter_registration_number = CASE
            WHEN LTRIM(voter_registration_number, '0') = '' THEN '0'
            ELSE LTRIM(voter_registration_number, '0')
        END
        WHERE voter_registration_number ~ '^0'
        """
    )


def downgrade() -> None:
    """Downgrade is not supported — original leading zeros are not recoverable."""
    raise NotImplementedError("Cannot restore original leading zeros. Restore from a database backup if needed.")
