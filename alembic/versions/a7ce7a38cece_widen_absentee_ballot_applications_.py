"""Widen absentee_ballot_applications columns for real GA SoS data

Real GA SoS absentee files use precinct *names* (e.g., "OLIVE BRANCH BAPTIST
CHURCH") rather than numeric codes, and some street-number fields contain full
addresses.  Widen the four affected columns to accommodate actual data.

Revision ID: a7ce7a38cece
Revises: 042
Create Date: 2026-03-11 23:07:49.858554
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7ce7a38cece"
down_revision: str | None = "042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "absentee_ballot_applications",
        "street_number",
        type_=sa.String(50),
        existing_type=sa.String(20),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "mailing_street_number",
        type_=sa.String(50),
        existing_type=sa.String(20),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "municipal_precinct",
        type_=sa.String(100),
        existing_type=sa.String(20),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "county_precinct",
        type_=sa.String(100),
        existing_type=sa.String(20),
    )


def downgrade() -> None:
    op.alter_column(
        "absentee_ballot_applications",
        "county_precinct",
        type_=sa.String(20),
        existing_type=sa.String(100),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "municipal_precinct",
        type_=sa.String(20),
        existing_type=sa.String(100),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "mailing_street_number",
        type_=sa.String(20),
        existing_type=sa.String(50),
    )
    op.alter_column(
        "absentee_ballot_applications",
        "street_number",
        type_=sa.String(20),
        existing_type=sa.String(50),
    )
