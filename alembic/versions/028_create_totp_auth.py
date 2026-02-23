"""Create TOTP authentication tables.

Revision ID: 028
Revises: 027
Create Date: 2026-02-22

Creates two tables:
1. totp_credentials — encrypted TOTP secret + lockout/replay state per user
2. totp_recovery_codes — one-time bypass codes generated at enrollment
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "028"
down_revision: str = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create totp_credentials and totp_recovery_codes tables."""
    op.create_table(
        "totp_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("encrypted_secret", sa.Text, nullable=False),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_otp", sa.String(6), nullable=True),
        sa.Column("last_used_otp_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_totp_credential_user_id"),
    )

    op.create_table(
        "totp_recovery_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_totp_recovery_codes_user_id", "totp_recovery_codes", ["user_id"])


def downgrade() -> None:
    """Drop TOTP tables."""
    op.drop_index("ix_totp_recovery_codes_user_id", table_name="totp_recovery_codes")
    op.drop_table("totp_recovery_codes")
    op.drop_table("totp_credentials")
