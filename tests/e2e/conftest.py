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
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from voter_api.core.config import Settings, get_settings
from voter_api.core.database import get_engine
from voter_api.core.security import create_access_token, hash_password
from voter_api.main import create_app, lifespan
from voter_api.models.boundary import Boundary
from voter_api.models.elected_official import ElectedOfficial
from voter_api.models.election import Election
from voter_api.models.user import User

# ---------------------------------------------------------------------------
# App & client
# ---------------------------------------------------------------------------

ADMIN_USERNAME = "e2e_admin"
ADMIN_EMAIL = "e2e_admin@test.com"
ADMIN_PASSWORD = "e2e-password-123"

ANALYST_USERNAME = "e2e_analyst"
VIEWER_USERNAME = "e2e_viewer"


@pytest.fixture(scope="session")
async def app() -> AsyncGenerator[FastAPI]:
    """Create the FastAPI app and run its lifespan to initialise the DB engine.

    The lifespan context manager calls ``init_engine()`` on entry and
    ``dispose_engine()`` on exit, so ``get_engine()`` is safe to call
    in any fixture or test that depends on ``app``.
    """
    _app = create_app()
    async with lifespan(_app):
        yield _app


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Return the live application settings."""
    return get_settings()


@pytest.fixture(scope="session")
def admin_token(settings: Settings) -> str:
    """JWT admin token matching the seeded admin user.

    Uses a 24-hour expiry so session-scoped tokens remain valid even for slow
    E2E runs (default is 30 minutes, which can expire mid-session).
    """
    return create_access_token(
        subject=ADMIN_USERNAME,
        role="admin",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=24 * 60,
    )


@pytest.fixture(scope="session")
def analyst_token(settings: Settings) -> str:
    """JWT analyst token (24-hour expiry for session-scoped use)."""
    return create_access_token(
        subject=ANALYST_USERNAME,
        role="analyst",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=24 * 60,
    )


@pytest.fixture(scope="session")
def viewer_token(settings: Settings) -> str:
    """JWT viewer token (24-hour expiry for session-scoped use)."""
    return create_access_token(
        subject=VIEWER_USERNAME,
        role="viewer",
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=24 * 60,
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client wired to the real FastAPI app via ASGI transport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e") as c:
        yield c


@pytest.fixture
async def admin_client(app: FastAPI, admin_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with admin Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


@pytest.fixture
async def analyst_client(app: FastAPI, analyst_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with analyst Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {analyst_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


@pytest.fixture
async def viewer_client(app: FastAPI, viewer_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with viewer Authorization header."""
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {viewer_token}"}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


# ---------------------------------------------------------------------------
# Database session for direct data seeding
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(app: FastAPI) -> AsyncGenerator[AsyncSession]:
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
async def seed_database(app: FastAPI, settings: Settings) -> AsyncGenerator[None]:
    """Seed test data once for the entire E2E session.

    Runs inside the app lifespan so the engine is already initialised.
    Uses SQLAlchemy Core inserts with ON CONFLICT DO UPDATE for
    idempotency—safe to run multiple times even if the DB has stale rows.
    """
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        hashed = hash_password(ADMIN_PASSWORD)

        # --- Users --------------------------------------------------------
        users_data = [
            {
                "id": ADMIN_USER_ID,
                "username": ADMIN_USERNAME,
                "email": ADMIN_EMAIL,
                "hashed_password": hashed,
                "role": "admin",
                "is_active": True,
            },
            {
                "id": ANALYST_USER_ID,
                "username": ANALYST_USERNAME,
                "email": "e2e_analyst@test.com",
                "hashed_password": hashed,
                "role": "analyst",
                "is_active": True,
            },
            {
                "id": VIEWER_USER_ID,
                "username": VIEWER_USERNAME,
                "email": "e2e_viewer@test.com",
                "hashed_password": hashed,
                "role": "viewer",
                "is_active": True,
            },
        ]
        for user_data in users_data:
            stmt = pg_insert(User).values(**user_data)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "username": stmt.excluded.username,
                    "email": stmt.excluded.email,
                    "hashed_password": stmt.excluded.hashed_password,
                    "role": stmt.excluded.role,
                    "is_active": stmt.excluded.is_active,
                },
            )
            await session.execute(stmt)

        # --- Election -----------------------------------------------------
        election_data = {
            "id": ELECTION_ID,
            "name": "E2E Test General Election",
            "election_date": date(2024, 11, 5),
            "election_type": "general",
            "district": "Statewide",
            "data_source_url": "https://results.enr.clarityelections.com/GA/test/json",
            "status": "active",
            "refresh_interval_seconds": 120,
        }
        stmt = pg_insert(Election).values(**election_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "election_date": stmt.excluded.election_date,
                "election_type": stmt.excluded.election_type,
                "district": stmt.excluded.district,
                "data_source_url": stmt.excluded.data_source_url,
                "status": stmt.excluded.status,
                "refresh_interval_seconds": stmt.excluded.refresh_interval_seconds,
            },
        )
        await session.execute(stmt)

        # --- Boundary (simple polygon in Georgia) -------------------------
        boundary_data = {
            "id": BOUNDARY_ID,
            "name": "E2E Test Congressional 1",
            "boundary_type": "congressional",
            "boundary_identifier": "1",
            "geometry": func.ST_GeomFromText(
                "MULTIPOLYGON(((-84.4 33.7, -84.3 33.7, -84.3 33.8, -84.4 33.8, -84.4 33.7)))",
                4326,
            ),
            "properties": {"district_number": "1"},
            "source": "e2e-test",
        }
        stmt = pg_insert(Boundary).values(**boundary_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": stmt.excluded.name,
                "boundary_type": stmt.excluded.boundary_type,
                "boundary_identifier": stmt.excluded.boundary_identifier,
                "geometry": boundary_data["geometry"],
                "properties": stmt.excluded.properties,
                "source": stmt.excluded.source,
            },
        )
        await session.execute(stmt)

        # --- Elected Official ---------------------------------------------
        official_data = {
            "id": OFFICIAL_ID,
            "boundary_type": "congressional",
            "district_identifier": "1",
            "full_name": "Jane E2E Doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "party": "Independent",
            "title": "Representative",
            "status": "auto",
        }
        stmt = pg_insert(ElectedOfficial).values(**official_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "boundary_type": stmt.excluded.boundary_type,
                "district_identifier": stmt.excluded.district_identifier,
                "full_name": stmt.excluded.full_name,
                "first_name": stmt.excluded.first_name,
                "last_name": stmt.excluded.last_name,
                "party": stmt.excluded.party,
                "title": stmt.excluded.title,
                "status": stmt.excluded.status,
            },
        )
        await session.execute(stmt)

        await session.commit()

    yield

    # Cleanup: remove seeded rows so the DB is left clean.
    async with factory() as session:
        await session.execute(delete(ElectedOfficial).where(ElectedOfficial.id == OFFICIAL_ID))
        await session.execute(delete(Boundary).where(Boundary.id == BOUNDARY_ID))
        await session.execute(delete(Election).where(Election.id == ELECTION_ID))
        await session.execute(delete(User).where(User.id.in_([ADMIN_USER_ID, ANALYST_USER_ID, VIEWER_USER_ID])))
        await session.commit()
