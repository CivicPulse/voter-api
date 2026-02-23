"""Create user_invites table.

Revision ID: 027
Revises: 026
Create Date: 2026-02-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "027"
down_revision: str = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_invites table."""
    op.create_table(
        "user_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column(
            "invited_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_user_invite_token_hash"),
    )
    op.create_index("ix_user_invites_email", "user_invites", ["email"])
    op.create_index("ix_user_invites_invited_by_id", "user_invites", ["invited_by_id"])


def downgrade() -> None:
    """Drop user_invites table."""
    op.drop_index("ix_user_invites_invited_by_id", table_name="user_invites")
    op.drop_index("ix_user_invites_email", table_name="user_invites")
    op.drop_table("user_invites")
