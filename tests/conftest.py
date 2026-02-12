"""Shared test fixtures for async database, sessions, HTTP client, and auth tokens."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from voter_api.core.config import Settings
from voter_api.core.security import create_access_token, hash_password
from voter_api.models.base import Base
from voter_api.models.user import User


@pytest.fixture
def settings() -> Settings:
    """Test application settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-for-production",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
    )


@pytest.fixture
async def async_engine(settings: Settings) -> AsyncGenerator[AsyncEngine]:
    """Create an in-memory async SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Create a per-test async session with transaction rollback."""
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def sample_user(async_session: AsyncSession) -> User:
    """Create a sample admin user in the test database."""
    user = User(
        id=uuid.uuid4(),
        username="testadmin",
        email="admin@test.com",
        hashed_password=hash_password("testpassword123"),
        role="admin",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
def admin_token(settings: Settings) -> str:
    """Generate a JWT access token for an admin user."""
    return create_access_token(
        subject="testadmin",
        role="admin",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture
def analyst_token(settings: Settings) -> str:
    """Generate a JWT access token for an analyst user."""
    return create_access_token(
        subject="testanalyst",
        role="analyst",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture
def viewer_token(settings: Settings) -> str:
    """Generate a JWT access token for a viewer user."""
    return create_access_token(
        subject="testviewer",
        role="viewer",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
