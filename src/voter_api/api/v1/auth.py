"""Authentication API endpoints.

POST /auth/login, POST /auth/refresh, GET /auth/me,
GET /users, POST /users, GET /health, GET /info.
"""

import math
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api import __version__
from voter_api.core.config import Settings, get_settings
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.models.user import User
from voter_api.schemas.auth import RefreshRequest, TokenResponse, UserCreateRequest, UserResponse
from voter_api.schemas.common import PaginationMeta, PaginationParams
from voter_api.services import auth_service


def _get_git_commit() -> str:
    """Resolve the current git short SHA once at import time."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(__file__).resolve().parent,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


_GIT_COMMIT = _get_git_commit()

router = APIRouter(tags=["auth"])


@router.get("/health", status_code=200)
async def health_check() -> dict:
    """Health check endpoint (no authentication required)."""
    return {"status": "healthy"}


@router.get("/info", status_code=200)
async def info(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """Return application version, git commit, and environment."""
    return {
        "version": __version__,
        "git_commit": _GIT_COMMIT,
        "environment": settings.environment,
    }


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate user and return JWT tokens."""
    user = await auth_service.authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_service.generate_tokens(user, settings)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Refresh an access token using a refresh token."""
    try:
        return await auth_service.refresh_access_token(session, request.refresh_token, settings)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the currently authenticated user's profile."""
    return current_user


@router.get("/users", response_model=dict)
async def list_users(
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pagination: Annotated[PaginationParams, Depends()],
) -> dict:
    """List all users (admin only)."""
    users, total = await auth_service.list_users(session, pagination.page, pagination.page_size)
    return {
        "items": [UserResponse.model_validate(u) for u in users],
        "pagination": PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=max(1, math.ceil(total / pagination.page_size)),
        ),
    }


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    request: UserCreateRequest,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Create a new user (admin only)."""
    try:
        return await auth_service.create_user(session, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
