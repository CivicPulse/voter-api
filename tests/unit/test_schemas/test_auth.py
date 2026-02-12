"""Unit tests for auth Pydantic schemas."""

import pytest
from pydantic import ValidationError

from voter_api.schemas.auth import LoginRequest, TokenResponse, UserCreateRequest


class TestLoginRequest:
    """Tests for LoginRequest validation."""

    def test_valid(self) -> None:
        """Valid login request."""
        req = LoginRequest(username="testuser", password="password123")
        assert req.username == "testuser"

    def test_short_username_rejected(self) -> None:
        """Username under 3 chars is rejected."""
        with pytest.raises(ValidationError):
            LoginRequest(username="ab", password="password123")

    def test_short_password_rejected(self) -> None:
        """Password under 8 chars is rejected."""
        with pytest.raises(ValidationError):
            LoginRequest(username="testuser", password="short")


class TestUserCreateRequest:
    """Tests for UserCreateRequest validation."""

    def test_valid(self) -> None:
        """Valid user creation request."""
        req = UserCreateRequest(
            username="newuser",
            email="new@test.com",
            password="password123",
            role="admin",
        )
        assert req.role == "admin"

    def test_invalid_role_rejected(self) -> None:
        """Invalid role is rejected."""
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="newuser",
                email="new@test.com",
                password="password123",
                role="superadmin",
            )

    def test_invalid_email_rejected(self) -> None:
        """Invalid email format is rejected."""
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="newuser",
                email="not-an-email",
                password="password123",
                role="viewer",
            )


class TestTokenResponse:
    """Tests for TokenResponse."""

    def test_construction(self) -> None:
        """TokenResponse holds correct values."""
        resp = TokenResponse(access_token="abc", refresh_token="def", expires_in=1800)
        assert resp.token_type == "bearer"
        assert resp.expires_in == 1800
