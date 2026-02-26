"""Add election metadata columns for enrichment.

Adds 9 nullable columns to the elections table: description, purpose,
eligibility_description, registration_deadline, early_voting_start,
early_voting_end, absentee_request_deadline, qualifying_start, qualifying_end.

Revision ID: 038
Revises: 037
Create Date: 2026-02-25
"""

import sqlalchemy as sa
from alembic import op

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("elections", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("elections", sa.Column("purpose", sa.Text(), nullable=True))
    op.add_column("elections", sa.Column("eligibility_description", sa.Text(), nullable=True))
    op.add_column("elections", sa.Column("registration_deadline", sa.Date(), nullable=True))
    op.add_column("elections", sa.Column("early_voting_start", sa.Date(), nullable=True))
    op.add_column("elections", sa.Column("early_voting_end", sa.Date(), nullable=True))
    op.add_column("elections", sa.Column("absentee_request_deadline", sa.Date(), nullable=True))
    op.add_column("elections", sa.Column("qualifying_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("elections", sa.Column("qualifying_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("elections", "qualifying_end")
    op.drop_column("elections", "qualifying_start")
    op.drop_column("elections", "absentee_request_deadline")
    op.drop_column("elections", "early_voting_end")
    op.drop_column("elections", "early_voting_start")
    op.drop_column("elections", "registration_deadline")
    op.drop_column("elections", "eligibility_description")
    op.drop_column("elections", "purpose")
    op.drop_column("elections", "description")
