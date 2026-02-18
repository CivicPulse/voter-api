"""widen voter columns to accommodate real GA SoS data

Revision ID: 020
Revises: 019
Create Date: 2026-02-17

Widens race (20→50), residence_street_number (20→50), and
mailing_street_number (20→50) to fit actual GA Secretary of State
voter file values (e.g. "ASIAN/PACIFIC ISLANDER" for race,
long street numbers like "25" chars for addresses).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: str | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("voters", "race", type_=sa.String(50), existing_type=sa.String(20))
    op.alter_column("voters", "residence_street_number", type_=sa.String(50), existing_type=sa.String(20))
    op.alter_column("voters", "mailing_street_number", type_=sa.String(50), existing_type=sa.String(20))


def downgrade() -> None:
    op.alter_column("voters", "race", type_=sa.String(20), existing_type=sa.String(50))
    op.alter_column("voters", "residence_street_number", type_=sa.String(20), existing_type=sa.String(50))
    op.alter_column("voters", "mailing_street_number", type_=sa.String(20), existing_type=sa.String(50))
