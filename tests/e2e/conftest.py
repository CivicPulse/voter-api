"""E2E test fixtures: real PostGIS database, Alembic migrations, seeded data.

These tests run against a live PostgreSQL/PostGIS database.  The CI workflow
runs ``alembic upgrade head`` before pytest, so tables already exist.
Fixtures seed baseline data and provide authenticated HTTP clients.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from voter_api.core.config import get_settings
from voter_api.core.database import get_engine
from voter_api.core.security import create_access_token, hash_password
from voter_api.main import create_app

# ---------------------------------------------------------------------------
# App & client
# ---------------------------------------------------------------------------

ADMIN_USERNAME = "e2e_admin"
ADMIN_EMAIL = "e2e_admin@test.com"
ADMIN_PASSWORD = "e2e-password-123"

ANALYST_USERNAME = "e2e_analyst"
VIEWER_USERNAME = "e2e_viewer"


@pytest.fixture(scope="session")
def app():
    """Create the FastAPI application (triggers lifespan / engine init)."""
    return create_app()


@pytest.fixture(scope="session")
def settings():
    """Return the live application settings."""
    return get_settings()


@pytest.fixture(scope="session")
def admin_token(settings) -> str:
    """JWT admin token matching the seeded admin user."""
    return create_access_token(
        subject=ADMIN_USERNAME,
        role="admin",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture(scope="session")
def analyst_token(settings) -> str:
    """JWT analyst token."""
    return create_access_token(
        subject=ANALYST_USERNAME,
        role="analyst",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture(scope="session")
def viewer_token(settings) -> str:
    """JWT viewer token."""
    return create_access_token(
        subject=VIEWER_USERNAME,
        role="viewer",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture
async def client(app) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client wired to the real FastAPI app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e") as c:
        yield c


@pytest.fixture
async def admin_client(app, admin_token) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with admin Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


@pytest.fixture
async def analyst_client(app, analyst_token) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with analyst Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {analyst_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


@pytest.fixture
async def viewer_client(app, viewer_token) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with viewer Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {viewer_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


# ---------------------------------------------------------------------------
# Database session for direct data seeding
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(app) -> AsyncGenerator[AsyncSession]:
    """Yield a real async DB session for seeding / assertions."""
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

# Fixed UUIDs so tests can reference them deterministically.
ADMIN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ANALYST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
VIEWER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
ELECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
OFFICIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
BOUNDARY_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")


@pytest.fixture(scope="session", autouse=True)
async def seed_database(app, settings):
    """Seed test data once for the entire E2E session.

    Runs inside the app lifespan so the engine is already initialised.
    Uses raw SQL with ON CONFLICT DO NOTHING for idempotency—safe to run
    multiple times if the DB is not torn down between runs.
    """
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        # --- Users --------------------------------------------------------
        hashed = hash_password(ADMIN_PASSWORD)
        await session.execute(
            text("""
                INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at)
                VALUES
                    (:admin_id, :admin_user, :admin_email, :hashed, 'admin', true, now()),
                    (:analyst_id, :analyst_user, 'e2e_analyst@test.com', :hashed, 'analyst', true, now()),
                    (:viewer_id, :viewer_user, 'e2e_viewer@test.com', :hashed, 'viewer', true, now())
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "admin_id": str(ADMIN_USER_ID),
                "admin_user": ADMIN_USERNAME,
                "admin_email": ADMIN_EMAIL,
                "hashed": hashed,
                "analyst_id": str(ANALYST_USER_ID),
                "analyst_user": ANALYST_USERNAME,
                "viewer_id": str(VIEWER_USER_ID),
                "viewer_user": VIEWER_USERNAME,
            },
        )

        # --- Election -----------------------------------------------------
        await session.execute(
            text("""
                INSERT INTO elections
                    (id, name, election_date, election_type, district,
                     data_source_url, status, refresh_interval_seconds, created_at, updated_at)
                VALUES
                    (:id, 'E2E Test General Election', :edate, 'general', 'Statewide',
                     'https://results.enr.clarityelections.com/GA/test/json',
                     'active', 120, now(), now())
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": str(ELECTION_ID), "edate": date(2024, 11, 5)},
        )

        # --- Boundary (simple polygon in Georgia) -------------------------
        await session.execute(
            text("""
                INSERT INTO boundaries
                    (id, name, boundary_type, boundary_identifier,
                     geometry, properties, source, created_at, updated_at)
                VALUES
                    (:id, 'E2E Test Congressional 1', 'congressional', '1',
                     ST_GeomFromText(
                         'MULTIPOLYGON(((-84.4 33.7, -84.3 33.7, -84.3 33.8, -84.4 33.8, -84.4 33.7)))',
                         4326
                     ),
                     '{"district_number": "1"}'::jsonb,
                     'e2e-test', now(), now())
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": str(BOUNDARY_ID)},
        )

        # --- Elected Official ---------------------------------------------
        await session.execute(
            text("""
                INSERT INTO elected_officials
                    (id, boundary_type, district_identifier, full_name,
                     first_name, last_name, party, title, status, created_at, updated_at)
                VALUES
                    (:id, 'congressional', '1', 'Jane E2E Doe',
                     'Jane', 'Doe', 'Independent', 'Representative',
                     'auto', now(), now())
                ON CONFLICT (id) DO NOTHING
            """),
            {"id": str(OFFICIAL_ID)},
        )

        await session.commit()

    yield

    # Cleanup: remove seeded rows so the DB is left clean.
    async with factory() as session:
        for table, uid in [
            ("elected_officials", OFFICIAL_ID),
            ("boundaries", BOUNDARY_ID),
            ("elections", ELECTION_ID),
            ("users", ADMIN_USER_ID),
            ("users", ANALYST_USER_ID),
            ("users", VIEWER_USER_ID),
        ]:
            await session.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": str(uid)})  # noqa: S608
        await session.commit()
