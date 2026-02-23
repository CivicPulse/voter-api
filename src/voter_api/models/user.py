"""User model for authentication and role-based access control."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from voter_api.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from voter_api.models.auth_tokens import PasswordResetToken, UserInvite
    from voter_api.models.passkey import Passkey
    from voter_api.models.totp import TOTPCredential, TOTPRecoveryCode


class User(Base, UUIDMixin):
    """Authenticated user of the system with role-based access control."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Auth token relationships
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sent_invites: Mapped[list[UserInvite]] = relationship(
        "UserInvite",
        back_populates="invited_by",
        foreign_keys="UserInvite.invited_by_id",
    )

    # TOTP relationships
    totp_credential: Mapped[TOTPCredential | None] = relationship(
        "TOTPCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    totp_recovery_codes: Mapped[list[TOTPRecoveryCode]] = relationship(
        "TOTPRecoveryCode",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Passkey relationships
    passkeys: Mapped[list[Passkey]] = relationship(
        "Passkey",
        back_populates="user",
        cascade="all, delete-orphan",
    )
