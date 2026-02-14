"""FastAPI dependency injection for database sessions, auth, and access control.

Provides get_async_session, get_current_user, and role-based access control
factories. Includes field-level access control for data sensitivity tiers (FR-024).
"""

from collections.abc import AsyncGenerator, Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.config import Settings, get_settings
from voter_api.core.database import get_session_factory
from voter_api.core.security import decode_token
from voter_api.core.sensitivity import SensitivityTier
from voter_api.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    """Yield an async database session with per-request lifecycle."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Decode JWT and return the authenticated user.

    Args:
        token: The JWT bearer token.
        session: The database session.
        settings: Application settings.

    Returns:
        The authenticated User model instance.

    Raises:
        HTTPException: If the token is invalid or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, settings.jwt_secret_key, settings.jwt_algorithm)
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except Exception as exc:
        raise credentials_exception from exc

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*roles: str) -> Callable[..., Any]:
    """Factory that creates a dependency requiring specific user roles.

    Args:
        *roles: Allowed role names (e.g., "admin", "analyst", "viewer").

    Returns:
        A FastAPI dependency function that validates the user's role.
    """

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' does not have access to this resource",
            )
        return current_user

    return role_checker


def filter_by_sensitivity(data: dict[str, Any], user_role: str, schema_class: type[BaseModel]) -> dict[str, Any]:
    """Filter response fields based on user role and data sensitivity tier.

    Viewers can only see government-sourced fields. Analysts and admins
    see all fields.

    Args:
        data: The response data dictionary.
        user_role: The requesting user's role.
        schema_class: The Pydantic schema class with field metadata.

    Returns:
        Filtered data dictionary.
    """
    if user_role in ("admin", "analyst"):
        return data

    filtered = {}
    for field_name, field_info in schema_class.model_fields.items():
        extra = field_info.json_schema_extra
        metadata = extra if isinstance(extra, dict) else {}
        tier = metadata.get("sensitivity_tier")
        if tier != SensitivityTier.SYSTEM_GENERATED.value:
            filtered[field_name] = data.get(field_name)
    return filtered
