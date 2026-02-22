"""Authentication and user management service.

Handles user authentication, creation, token generation, and refresh.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.config import Settings
from voter_api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from voter_api.models.user import User
from voter_api.schemas.auth import TokenResponse, UserCreateRequest

_UPDATABLE_USER_FIELDS: frozenset[str] = frozenset({"email", "role", "is_active"})


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User | None:
    """Authenticate a user by username and password.

    Args:
        session: The database session.
        username: The username to authenticate.
        password: The plaintext password.

    Returns:
        The User if authentication succeeds, None otherwise.
    """
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user


async def create_user(session: AsyncSession, request: UserCreateRequest) -> User:
    """Create a new user.

    Args:
        session: The database session.
        request: User creation request data.

    Returns:
        The created User.

    Raises:
        ValueError: If username or email already exists.
    """
    existing = await session.execute(
        select(User).where((User.username == request.username) | (User.email == request.email))
    )
    if existing.scalar_one_or_none() is not None:
        msg = "Username or email already exists"
        raise ValueError(msg)

    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role=request.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def list_users(session: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
    """List users with pagination.

    Args:
        session: The database session.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (users list, total count).
    """
    count_result = await session.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(select(User).offset(offset).limit(page_size).order_by(User.created_at))
    users = list(result.scalars().all())
    return users, total


def generate_tokens(user: User, settings: Settings) -> TokenResponse:
    """Generate access and refresh tokens for a user.

    Args:
        user: The authenticated user.
        settings: Application settings.

    Returns:
        Token response with access and refresh tokens.
    """
    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh_token = create_refresh_token(
        subject=user.username,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_days=settings.jwt_refresh_token_expire_days,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


async def refresh_access_token(
    session: AsyncSession,
    refresh_token_str: str,
    settings: Settings,
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    Args:
        session: The database session.
        refresh_token_str: The refresh token string.
        settings: Application settings.

    Returns:
        New token response.

    Raises:
        ValueError: If the refresh token is invalid or user not found.
    """
    try:
        payload = decode_token(refresh_token_str, settings.jwt_secret_key, settings.jwt_algorithm)
    except Exception as e:
        msg = "Invalid refresh token"
        raise ValueError(msg) from e

    if payload.get("type") != "refresh":
        msg = "Token is not a refresh token"
        raise ValueError(msg)

    username = payload.get("sub")
    if username is None:
        msg = "Invalid token payload"
        raise ValueError(msg)

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        msg = "User not found or inactive"
        raise ValueError(msg)

    return generate_tokens(user, settings)


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Get a user by ID.

    Args:
        session: The database session.
        user_id: The UUID of the user to retrieve.

    Returns:
        The User if found, None otherwise.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(session: AsyncSession, user: User, updates: dict) -> User:
    """Update a user's fields.

    Args:
        session: The database session.
        user: The User to update.
        updates: Dictionary of field names to new values.

    Returns:
        The updated User.

    Raises:
        ValueError: If the new email is already in use by another user.
    """
    if "email" in updates and updates["email"] != user.email:
        existing = await session.execute(select(User).where(User.email == updates["email"]))
        if existing.scalar_one_or_none() is not None:
            msg = "Email already in use"
            raise ValueError(msg)

    for field, value in updates.items():
        if field in _UPDATABLE_USER_FIELDS:
            setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    """Delete a user account.

    Args:
        session: The database session.
        user: The User to delete.
    """
    await session.delete(user)
    await session.commit()
