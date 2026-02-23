"""Shared fixtures for integration API tests.

Provides mock session, mock users, client factories, and a ``make_test_app``
helper so individual test modules only need to specify which router to mount.
"""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.core.dependencies import get_async_session, get_current_user


def make_test_app(
    router,
    mock_session: AsyncMock,
    *,
    user: MagicMock | None = None,
) -> FastAPI:
    """Create a minimal FastAPI app with the given router and dependency overrides."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def mock_admin_user() -> MagicMock:
    """Mock admin user for dependency override."""
    user = MagicMock()
    user.role = "admin"
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.username = "admin"
    user.is_active = True
    return user


@pytest.fixture
def mock_viewer_user() -> MagicMock:
    """Mock viewer user for dependency override."""
    user = MagicMock()
    user.role = "viewer"
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    user.username = "viewer"
    user.is_active = True
    return user


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client (no auth)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with admin auth."""
    async with AsyncClient(
        transport=ASGITransport(app=admin_app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with viewer auth."""
    async with AsyncClient(
        transport=ASGITransport(app=viewer_app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c
