"""Create passkeys table.

Revision ID: 028
Revises: 027
Create Date: 2026-02-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "028"
down_revision: str = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create passkeys table."""
    op.create_table(
        "passkeys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.LargeBinary, nullable=False),
        sa.Column("public_key", sa.LargeBinary, nullable=False),
        sa.Column("sign_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("credential_id", name="uq_passkey_credential_id"),
    )
    op.create_index("ix_passkeys_user_id", "passkeys", ["user_id"])
    op.create_index("ix_passkeys_credential_id", "passkeys", ["credential_id"])


def downgrade() -> None:
    """Drop passkeys table."""
    op.drop_index("ix_passkeys_credential_id", table_name="passkeys")
    op.drop_index("ix_passkeys_user_id", table_name="passkeys")
    op.drop_table("passkeys")
