"""Unit tests for JWT and password security module."""

import pytest

from voter_api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Tests for bcrypt password hashing and verification."""

    def test_hash_and_verify(self) -> None:
        """Hashed password can be verified."""
        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed)

    def test_wrong_password_fails(self) -> None:
        """Wrong password fails verification."""
        hashed = hash_password("mypassword123")
        assert not verify_password("wrongpassword", hashed)

    def test_hash_is_different_each_time(self) -> None:
        """Same password produces different hashes (salt)."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


class TestJWT:
    """Tests for JWT token creation and decoding."""

    SECRET = "test-secret-key"

    def test_create_and_decode_access_token(self) -> None:
        """Access token can be created and decoded."""
        token = create_access_token("testuser", "admin", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self) -> None:
        """Refresh token can be created and decoded."""
        token = create_refresh_token("testuser", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "testuser"
        assert payload["type"] == "refresh"

    def test_decode_with_wrong_secret_fails(self) -> None:
        """Decoding with wrong secret raises an error."""
        import jwt as pyjwt

        token = create_access_token("user", "admin", self.SECRET)
        with pytest.raises(pyjwt.InvalidSignatureError):
            decode_token(token, "wrong-secret")

    def test_expired_token_fails(self) -> None:
        """Expired token raises an error."""
        import jwt as pyjwt

        token = create_access_token("user", "admin", self.SECRET, expires_minutes=-1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token, self.SECRET)
