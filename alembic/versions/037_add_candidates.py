"""Add candidates and candidate_links tables.

Revision ID: 037
Revises: 036
Create Date: 2026-02-25
"""

import sqlalchemy as sa
from alembic import op

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("election_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("party", sa.String(50), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("ballot_order", sa.Integer(), nullable=True),
        sa.Column("filing_status", sa.String(20), nullable=False, server_default="qualified"),
        sa.Column("is_incumbent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sos_ballot_option_id", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["election_id"], ["elections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("election_id", "full_name", name="uq_candidate_election_name"),
        sa.CheckConstraint(
            "filing_status IN ('qualified', 'withdrawn', 'disqualified', 'write_in')",
            name="ck_candidate_filing_status",
        ),
    )
    op.create_index("ix_candidates_election_id", "candidates", ["election_id"])
    op.create_index("ix_candidates_filing_status", "candidates", ["filing_status"])
    op.create_index(
        "ix_candidates_sos_ballot_option_id",
        "candidates",
        ["sos_ballot_option_id"],
        postgresql_where=sa.text("sos_ballot_option_id IS NOT NULL"),
    )

    op.create_table(
        "candidate_links",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("link_type", sa.String(20), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("label", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "link_type IN ('website', 'campaign', 'facebook', 'twitter', 'instagram', 'youtube', 'linkedin', 'other')",
            name="ck_candidate_link_type",
        ),
    )
    op.create_index("ix_candidate_links_candidate_id", "candidate_links", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("candidate_links")
    op.drop_table("candidates")
