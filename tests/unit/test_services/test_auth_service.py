"""Tests for the authentication service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.core.config import Settings
from voter_api.schemas.auth import TokenResponse, UserCreateRequest
from voter_api.services.auth_service import (
    authenticate_user,
    create_user,
    delete_user,
    generate_tokens,
    get_user,
    list_users,
    refresh_access_token,
    update_user,
)


def _mock_settings() -> Settings:
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-for-production",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
    )


def _mock_user(**overrides: object) -> MagicMock:
    """Create a mock User object."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.email = "test@example.com"
    user.hashed_password = "$2b$12$hashed"
    user.role = "admin"
    user.is_active = True
    user.last_login_at = None
    user.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(user, key, value)
    return user


def _mock_session_with_result(scalar_result: object) -> AsyncMock:
    """Create mock session returning a specific scalar result."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    session.execute.return_value = result
    return session


class TestAuthenticateUser:
    """Tests for authenticate_user."""

    @pytest.mark.asyncio
    async def test_valid_credentials_returns_user(self) -> None:
        user = _mock_user()
        session = _mock_session_with_result(user)

        with patch("voter_api.services.auth_service.verify_password", return_value=True):
            result = await authenticate_user(session, "testuser", "password123")

        assert result is user
        assert user.last_login_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrong_password_returns_none(self) -> None:
        user = _mock_user()
        session = _mock_session_with_result(user)

        with patch("voter_api.services.auth_service.verify_password", return_value=False):
            result = await authenticate_user(session, "testuser", "wrongpassword")

        assert result is None

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_none(self) -> None:
        session = _mock_session_with_result(None)

        with patch("voter_api.services.auth_service.verify_password", return_value=False):
            result = await authenticate_user(session, "nobody", "password")

        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user_returns_none(self) -> None:
        user = _mock_user(is_active=False)
        session = _mock_session_with_result(user)

        with patch("voter_api.services.auth_service.verify_password", return_value=True):
            result = await authenticate_user(session, "testuser", "password123")

        assert result is None


class TestCreateUser:
    """Tests for create_user."""

    @pytest.mark.asyncio
    async def test_creates_new_user(self) -> None:
        session = AsyncMock()
        # First execute returns None (no existing user)
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = None
        session.execute.return_value = first_result

        request = UserCreateRequest(
            username="newuser",
            email="new@example.com",
            password="password123",
            role="viewer",
        )

        with patch("voter_api.services.auth_service.hash_password", return_value="hashed"):
            await create_user(session, request)

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_username_raises_error(self) -> None:
        existing_user = _mock_user()
        session = _mock_session_with_result(existing_user)

        request = UserCreateRequest(
            username="testuser",
            email="new@example.com",
            password="password123",
            role="viewer",
        )

        with pytest.raises(ValueError, match="Username or email already exists"):
            await create_user(session, request)


class TestListUsers:
    """Tests for list_users."""

    @pytest.mark.asyncio
    async def test_returns_users_and_count(self) -> None:
        session = AsyncMock()
        users = [_mock_user(), _mock_user(username="user2")]

        # First call: count query, second call: select query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = users
        session.execute.side_effect = [count_result, select_result]

        result_users, total = await list_users(session, page=1, page_size=20)
        assert total == 2
        assert len(result_users) == 2

    @pytest.mark.asyncio
    async def test_pagination_offset(self) -> None:
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_users, total = await list_users(session, page=2, page_size=10)
        assert total == 0
        assert result_users == []


class TestGenerateTokens:
    """Tests for generate_tokens."""

    def test_generates_access_and_refresh_tokens(self) -> None:
        user = _mock_user()
        settings = _mock_settings()

        result = generate_tokens(user, settings)

        assert isinstance(result, TokenResponse)
        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        assert result.expires_in == 30 * 60

    def test_different_users_get_different_tokens(self) -> None:
        settings = _mock_settings()
        user1 = _mock_user(username="user1")
        user2 = _mock_user(username="user2")

        tokens1 = generate_tokens(user1, settings)
        tokens2 = generate_tokens(user2, settings)

        assert tokens1.access_token != tokens2.access_token


class TestRefreshAccessToken:
    """Tests for refresh_access_token."""

    @pytest.mark.asyncio
    async def test_valid_refresh_token_returns_new_tokens(self) -> None:
        user = _mock_user()
        settings = _mock_settings()
        session = _mock_session_with_result(user)

        from voter_api.core.security import create_refresh_token

        refresh_token = create_refresh_token(
            subject="testuser",
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        result = await refresh_access_token(session, refresh_token, settings)
        assert isinstance(result, TokenResponse)
        assert result.access_token
        assert result.refresh_token

    @pytest.mark.asyncio
    async def test_invalid_token_raises_error(self) -> None:
        settings = _mock_settings()
        session = AsyncMock()

        with pytest.raises(ValueError, match="Invalid refresh token"):
            await refresh_access_token(session, "invalid-token", settings)

    @pytest.mark.asyncio
    async def test_non_refresh_token_raises_error(self) -> None:
        settings = _mock_settings()
        session = AsyncMock()

        # Create an access token (not a refresh token)
        from voter_api.core.security import create_access_token

        access_token = create_access_token(
            subject="testuser",
            role="admin",
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(ValueError, match="Token is not a refresh token"):
            await refresh_access_token(session, access_token, settings)

    @pytest.mark.asyncio
    async def test_user_not_found_raises_error(self) -> None:
        settings = _mock_settings()
        session = _mock_session_with_result(None)

        from voter_api.core.security import create_refresh_token

        refresh_token = create_refresh_token(
            subject="nonexistent",
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(ValueError, match="User not found or inactive"):
            await refresh_access_token(session, refresh_token, settings)

    @pytest.mark.asyncio
    async def test_inactive_user_raises_error(self) -> None:
        user = _mock_user(is_active=False)
        settings = _mock_settings()
        session = _mock_session_with_result(user)

        from voter_api.core.security import create_refresh_token

        refresh_token = create_refresh_token(
            subject="testuser",
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(ValueError, match="User not found or inactive"):
            await refresh_access_token(session, refresh_token, settings)


class TestGetUser:
    """Tests for get_user."""

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self) -> None:
        user = _mock_user()
        session = _mock_session_with_result(user)

        result = await get_user(session, user.id)

        assert result is user

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = _mock_session_with_result(None)

        result = await get_user(session, uuid.uuid4())

        assert result is None


class TestUpdateUser:
    """Tests for update_user."""

    @pytest.mark.asyncio
    async def test_updates_allowed_fields(self) -> None:
        user = _mock_user()
        session = AsyncMock()

        # No email change, so no uniqueness check needed
        await update_user(session, user, {"role": "analyst", "is_active": False})

        assert user.role == "analyst"
        assert user.is_active is False
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(user)

    @pytest.mark.asyncio
    async def test_email_conflict_raises_error(self) -> None:
        user = _mock_user(email="original@example.com")
        other_user = _mock_user(email="taken@example.com")
        session = _mock_session_with_result(other_user)

        with pytest.raises(ValueError, match="Email already in use"):
            await update_user(session, user, {"email": "taken@example.com"})

    @pytest.mark.asyncio
    async def test_same_email_skips_uniqueness_check(self) -> None:
        user = _mock_user(email="same@example.com")
        session = AsyncMock()

        # Updating to the same email should not query for conflicts
        await update_user(session, user, {"email": "same@example.com"})

        session.execute.assert_not_awaited()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_updatable_fields(self) -> None:
        user = _mock_user()
        session = AsyncMock()

        await update_user(session, user, {"username": "hacker"})

        # username is not in _UPDATABLE_USER_FIELDS — must not be set
        assert user.username == "testuser"
        session.commit.assert_awaited_once()


class TestDeleteUser:
    """Tests for delete_user."""

    @pytest.mark.asyncio
    async def test_deletes_user(self) -> None:
        user = _mock_user()
        session = AsyncMock()

        await delete_user(session, user)

        session.delete.assert_awaited_once_with(user)
        session.commit.assert_awaited_once()
