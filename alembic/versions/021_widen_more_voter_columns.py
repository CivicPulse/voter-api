"""widen additional voter columns for real GA SoS data

Revision ID: 021
Revises: 020
Create Date: 2026-02-17

Widens city_council_district (10→50) and mailing_zipcode (10→20)
to handle real-world GA SoS voter file values. Houston County data
contains values like "4-WARNER ROBINS" in city_council_district.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("voters", "city_council_district", type_=sa.String(50), existing_type=sa.String(10))
    op.alter_column("voters", "mailing_zipcode", type_=sa.String(20), existing_type=sa.String(10))


def downgrade() -> None:
    op.alter_column("voters", "city_council_district", type_=sa.String(10), existing_type=sa.String(50))
    op.alter_column("voters", "mailing_zipcode", type_=sa.String(20), existing_type=sa.String(10))
