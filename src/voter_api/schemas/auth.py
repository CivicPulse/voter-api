"""Authentication and user Pydantic v2 schemas.

Defines request/response schemas for login, token refresh, and user management.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request with username and password."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)


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
