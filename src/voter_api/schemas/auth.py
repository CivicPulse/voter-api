"""Authentication and user Pydantic v2 schemas.

Defines request/response schemas for login, token refresh, and user management.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request with username, password, and optional TOTP code."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)
    totp_code: str | None = None


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class TokenResponse(BaseModel):
    """JWT token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token expiration in seconds")


class UserCreateRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(pattern="^(admin|analyst|viewer|contributor)$")


class UserUpdateRequest(BaseModel):
    """Request to partially update an existing user (all fields optional)."""

    email: EmailStr | None = None
    role: str | None = Field(default=None, pattern="^(admin|analyst|viewer|contributor)$")
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User information response."""

    id: UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Password Reset ──────────────────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    """Request to initiate a password reset by email."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm a password reset using the token received by email."""

    token: str
    new_password: str = Field(min_length=8)


class MessageResponse(BaseModel):
    """Generic success message response."""

    message: str


# ── User Invites ────────────────────────────────────────────────────────────


class InviteCreate(BaseModel):
    """Admin request to invite a new user by email."""

    email: EmailStr
    role: Literal["admin", "analyst", "viewer"]


class InviteResponse(BaseModel):
    """Invite record returned from the API."""

    id: UUID
    email: str
    role: str
    invited_by_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedInvites(BaseModel):
    """Paginated list of pending invites."""

    items: list[InviteResponse]
    total: int
    page: int
    page_size: int


class InviteAccept(BaseModel):
    """Invitee request to accept an invite and create their account."""

    token: str
    username: str = Field(min_length=3)
    password: str = Field(min_length=8)


class InviteAcceptResponse(BaseModel):
    """Response after successfully accepting an invite."""

    message: str
    user: UserResponse


# ── TOTP ────────────────────────────────────────────────────────────────────


class TOTPEnrollmentResponse(BaseModel):
    """TOTP enrollment response with provisioning URI and QR code."""

    provisioning_uri: str
    qr_code_svg: str


class TOTPConfirmRequest(BaseModel):
    """Confirm TOTP enrollment with a valid 6-digit code."""

    code: str = Field(pattern=r"^[0-9]{6}$")


class TOTPConfirmResponse(BaseModel):
    """Response after confirming TOTP enrollment, includes one-time recovery codes."""

    recovery_codes: list[str]


class TOTPRecoveryCodesCountResponse(BaseModel):
    """Count of remaining (unused) TOTP recovery codes."""

    remaining_codes: int


class MFARequiredError(BaseModel):
    """Error response when TOTP is required or code was invalid."""

    detail: str
    error_code: Literal["mfa_required", "mfa_invalid"]


class TOTPLockedError(BaseModel):
    """Error response when TOTP is locked due to too many failed attempts."""

    detail: str
    locked_until: datetime


# ── Passkeys ────────────────────────────────────────────────────────────────


class PasskeyRegistrationOptionsResponse(BaseModel):
    """Passkey registration options and short-lived challenge token."""

    options: dict
    challenge_token: str


class PasskeyRegistrationVerifyRequest(BaseModel):
    """Verify a passkey registration response from the client."""

    credential_response: dict
    challenge_token: str
    name: str | None = Field(default=None, max_length=100)


class PasskeyResponse(BaseModel):
    """Registered passkey details."""

    id: UUID
    name: str | None
    registered_at: datetime
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class PasskeyRenameRequest(BaseModel):
    """Request to rename a passkey."""

    name: str = Field(max_length=100)


class PasskeyLoginOptionsRequest(BaseModel):
    """Username-first passkey login — request authentication options."""

    username: str


class PasskeyLoginOptionsResponse(BaseModel):
    """Passkey authentication options and short-lived challenge token."""

    options: dict
    challenge_token: str


class PasskeyLoginVerifyRequest(BaseModel):
    """Verify a passkey authentication assertion from the client."""

    username: str
    credential_response: dict
    challenge_token: str
