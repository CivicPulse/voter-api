"""E2E test fixtures: real PostGIS database, Alembic migrations, seeded data.

These tests run against a live PostgreSQL/PostGIS database.  The CI workflow
runs ``alembic upgrade head`` before pytest, so tables already exist.
Fixtures seed baseline data and provide authenticated HTTP clients.
"""

import hashlib
import os
import uuid
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
from voter_api.models.absentee_ballot import AbsenteeBallotApplication
from voter_api.models.auth_tokens import UserInvite
from voter_api.models.boundary import Boundary
from voter_api.models.candidate import Candidate, CandidateLink
from voter_api.models.elected_official import ElectedOfficial
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob
from voter_api.models.totp import TOTPCredential
from voter_api.models.user import User
from voter_api.models.voter import Voter
from voter_api.models.voter_history import VoterHistory

# ---------------------------------------------------------------------------
# App & client
# ---------------------------------------------------------------------------

ADMIN_USERNAME = "e2e_admin"
ADMIN_EMAIL = "e2e_admin@test.com"
ADMIN_PASSWORD = os.environ.get(  # noqa: S105
    "E2E_ADMIN_PASSWORD", "E2e-S3cur3-P@ssw0rd-2024!"
)

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


@asynccontextmanager
async def _make_client(app: FastAPI, token: str | None = None) -> AsyncGenerator[httpx.AsyncClient]:
    """Create an ASGI-wired httpx client with optional Bearer-token auth.

    Shared by all role-specific client fixtures to eliminate code duplication.
    """
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(transport=transport, base_url="http://e2e", headers=headers) as c:
        yield c


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client wired to the real FastAPI app via ASGI transport."""
    async with _make_client(app) as c:
        yield c


@pytest.fixture
async def admin_client(app: FastAPI, admin_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with admin Authorization header."""
    async with _make_client(app, admin_token) as c:
        yield c


@pytest.fixture
async def analyst_client(app: FastAPI, analyst_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with analyst Authorization header."""
    async with _make_client(app, analyst_token) as c:
        yield c


@pytest.fixture
async def viewer_client(app: FastAPI, viewer_token: str) -> AsyncGenerator[httpx.AsyncClient]:
    """Async HTTP client with viewer Authorization header."""
    async with _make_client(app, viewer_token) as c:
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
TOTP_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000004")
ELECTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
OFFICIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
BOUNDARY_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")
VOTER_ID = uuid.UUID("00000000-0000-0000-0000-000000000050")
INVITE_ID = uuid.UUID("00000000-0000-0000-0000-000000000040")
TOTP_CREDENTIAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000041")
IMPORT_JOB_ID = uuid.UUID("00000000-0000-0000-0000-000000000060")
VOTER_HISTORY_ID = uuid.UUID("00000000-0000-0000-0000-000000000061")
CANDIDATE_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
CANDIDATE_LINK_ID = uuid.UUID("00000000-0000-0000-0000-000000000071")
ABSENTEE_RECORD_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee01")
ABSENTEE_RECORD_ID_2 = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeee02")

TOTP_USERNAME = "e2e_totp_user"
INVITE_EMAIL = "e2e_invite@test.com"
# Raw invite token for E2E tests (hash stored in DB)
INVITE_TOKEN = "e2e_test_invite_token_abc123"


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
        # All three seeded users share the same hashed password for simplicity.
        # Each user has a distinct role; authentication tests use ADMIN_PASSWORD
        # for the admin login test and a hard-coded wrong value for failure tests.
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
        # Include the TOTP-enrolled user alongside the standard seeded users.
        users_data.append(
            {
                "id": TOTP_USER_ID,
                "username": TOTP_USERNAME,
                "email": "e2e_totp@test.com",
                "hashed_password": hashed,
                "role": "viewer",
                "is_active": True,
            }
        )

        # Pre-delete any users with matching usernames that may have a different
        # ID (e.g. from an incomplete prior run).  ON CONFLICT on the primary key
        # alone would miss unique violations on username/email columns.
        seeded_usernames = [u["username"] for u in users_data]
        await session.execute(delete(User).where(User.username.in_(seeded_usernames)))

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

        # --- TOTP credential for TOTP_USER -----------------------------------
        await session.execute(delete(TOTPCredential).where(TOTPCredential.user_id == TOTP_USER_ID))

        # Encrypt a known TOTP secret using the configured Fernet key so that
        # the credential can be decrypted by the real TOTPManager in E2E tests.
        fernet_key = settings.totp_secret_encryption_key or ""
        if fernet_key:
            from cryptography.fernet import Fernet

            encrypted_secret = (
                Fernet(fernet_key.encode() if isinstance(fernet_key, str) else fernet_key)
                .encrypt(b"JBSWY3DPEHPK3PXP")
                .decode()
            )
        else:
            encrypted_secret = "fake_encrypted_secret_for_e2e_tests"

        totp_cred_data = {
            "id": TOTP_CREDENTIAL_ID,
            "user_id": TOTP_USER_ID,
            "encrypted_secret": encrypted_secret,
            "is_verified": True,
            "failed_attempts": 0,
            "locked_until": None,
            "last_used_otp": None,
            "last_used_otp_at": None,
        }
        stmt = pg_insert(TOTPCredential).values(**totp_cred_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "user_id": stmt.excluded.user_id,
                "encrypted_secret": stmt.excluded.encrypted_secret,
                "is_verified": stmt.excluded.is_verified,
                "failed_attempts": stmt.excluded.failed_attempts,
            },
        )
        await session.execute(stmt)

        # --- Pending invite -----------------------------------------------
        now = datetime.now(UTC)
        invite_token_hash = hashlib.sha256(INVITE_TOKEN.encode()).hexdigest()
        await session.execute(delete(UserInvite).where(UserInvite.id == INVITE_ID))
        invite_data = {
            "id": INVITE_ID,
            "email": INVITE_EMAIL,
            "role": "viewer",
            "invited_by_id": ADMIN_USER_ID,
            "token_hash": invite_token_hash,
            "expires_at": now + timedelta(days=7),
            "accepted_at": None,
        }
        stmt = pg_insert(UserInvite).values(**invite_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "token_hash": stmt.excluded.token_hash,
                "expires_at": stmt.excluded.expires_at,
                "accepted_at": stmt.excluded.accepted_at,
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

        # --- Candidate (for seeded election) --------------------------------
        candidate_data = {
            "id": CANDIDATE_ID,
            "election_id": ELECTION_ID,
            "full_name": "E2E Test Candidate",
            "party": "Independent",
            "bio": "E2E test biographical info.",
            "filing_status": "qualified",
            "is_incumbent": False,
            "ballot_order": 1,
        }
        stmt = pg_insert(Candidate).values(**candidate_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "election_id": stmt.excluded.election_id,
                "full_name": stmt.excluded.full_name,
                "party": stmt.excluded.party,
                "bio": stmt.excluded.bio,
                "filing_status": stmt.excluded.filing_status,
                "is_incumbent": stmt.excluded.is_incumbent,
                "ballot_order": stmt.excluded.ballot_order,
            },
        )
        await session.execute(stmt)

        # --- Candidate Link -------------------------------------------------
        candidate_link_data = {
            "id": CANDIDATE_LINK_ID,
            "candidate_id": CANDIDATE_ID,
            "link_type": "campaign",
            "url": "https://e2e-test-campaign.com",
            "label": "Campaign Website",
        }
        stmt = pg_insert(CandidateLink).values(**candidate_link_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "candidate_id": stmt.excluded.candidate_id,
                "link_type": stmt.excluded.link_type,
                "url": stmt.excluded.url,
                "label": stmt.excluded.label,
            },
        )
        await session.execute(stmt)

        # --- Boundary (simple polygon in Georgia) -------------------------
        boundary_data = {
            "id": BOUNDARY_ID,
            "name": "E2E Test Congressional 99",
            "boundary_type": "congressional",
            "boundary_identifier": "099",
            "geometry": func.ST_GeomFromText(
                "MULTIPOLYGON(((-84.4 33.7, -84.3 33.7, -84.3 33.8, -84.4 33.8, -84.4 33.7)))",
                4326,
            ),
            "properties": {"district_number": "99"},
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

        # --- Voter (inside the seeded boundary polygon) --------------------
        voter_data = {
            "id": VOTER_ID,
            "county": "FULTON",
            "voter_registration_number": "E2E000001",
            "status": "A",
            "last_name": "E2ETEST",
            "first_name": "JANE",
            "congressional_district": "099",
            "residence_street_number": "100",
            "residence_street_name": "PEACHTREE",
            "residence_street_type": "ST",
            "residence_city": "ATLANTA",
            "residence_zipcode": "30303",
            "official_latitude": 33.75,
            "official_longitude": -84.35,
            "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.35, 33.75), 4326),
            "official_source": "e2e-seed",
        }
        stmt = pg_insert(Voter).values(**voter_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "county": stmt.excluded.county,
                "voter_registration_number": stmt.excluded.voter_registration_number,
                "status": stmt.excluded.status,
                "last_name": stmt.excluded.last_name,
                "first_name": stmt.excluded.first_name,
                "congressional_district": stmt.excluded.congressional_district,
                "official_latitude": stmt.excluded.official_latitude,
                "official_longitude": stmt.excluded.official_longitude,
                "official_point": voter_data["official_point"],
                "official_source": stmt.excluded.official_source,
            },
        )
        await session.execute(stmt)

        # --- Import Job (needed for voter_history FK) ----------------------
        import_job_data = {
            "id": IMPORT_JOB_ID,
            "file_name": "e2e_seed_history.csv",
            "file_type": "voter_history",
            "status": "completed",
            "total_records": 1,
            "records_succeeded": 1,
            "records_failed": 0,
            "records_inserted": 1,
            "records_updated": 0,
            "records_skipped": 0,
            "records_unmatched": 0,
            "triggered_by": ADMIN_USER_ID,
        }
        stmt = pg_insert(ImportJob).values(**import_job_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "file_name": stmt.excluded.file_name,
                "status": stmt.excluded.status,
            },
        )
        await session.execute(stmt)

        # --- Voter History (participation record for the seeded election) --
        # Pre-delete any stale VoterHistory row matching the participation key
        # to avoid a unique violation on uq_voter_history_participation when a
        # leftover row with a different id already exists.
        await session.execute(
            delete(VoterHistory).where(
                VoterHistory.voter_registration_number == "E2E000001",
                VoterHistory.election_date == date(2024, 11, 5),
                VoterHistory.election_type == "General Election",
            )
        )
        voter_history_data = {
            "id": VOTER_HISTORY_ID,
            "voter_registration_number": "E2E000001",
            "county": "FULTON",
            "election_date": date(2024, 11, 5),
            "election_type": "General Election",
            "normalized_election_type": "general",
            "party": None,
            "ballot_style": "FULTON-01",
            "absentee": False,
            "provisional": False,
            "supplemental": False,
            "election_id": ELECTION_ID,
            "import_job_id": IMPORT_JOB_ID,
        }
        stmt = pg_insert(VoterHistory).values(**voter_history_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "county": stmt.excluded.county,
                "election_id": stmt.excluded.election_id,
                "import_job_id": stmt.excluded.import_job_id,
            },
        )
        await session.execute(stmt)

        # --- Elected Official ---------------------------------------------
        official_data = {
            "id": OFFICIAL_ID,
            "boundary_type": "congressional",
            "district_identifier": "099",
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

        # --- Absentee Ballot Applications ----------------------------------
        absentee_data_1 = {
            "id": ABSENTEE_RECORD_ID,
            "county": "CHEROKEE",
            "voter_registration_number": "12345",
            "last_name": "SMITH",
            "first_name": "JOHN",
            "application_status": "A",
            "ballot_status": "I",
            "application_date": date(2024, 10, 1),
            "ballot_style": "CHEROKEE-01",
            "party": "NP",
            "import_job_id": IMPORT_JOB_ID,
        }
        stmt = pg_insert(AbsenteeBallotApplication).values(**absentee_data_1)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "county": stmt.excluded.county,
                "voter_registration_number": stmt.excluded.voter_registration_number,
                "application_status": stmt.excluded.application_status,
                "ballot_status": stmt.excluded.ballot_status,
                "import_job_id": stmt.excluded.import_job_id,
            },
        )
        await session.execute(stmt)

        absentee_data_2 = {
            "id": ABSENTEE_RECORD_ID_2,
            "county": "FULTON",
            "voter_registration_number": "67890",
            "last_name": "DOE",
            "first_name": "JANE",
            "application_status": "A",
            "ballot_status": "R",
            "application_date": date(2024, 10, 5),
            "ballot_style": "FULTON-01",
            "party": "D",
            "import_job_id": IMPORT_JOB_ID,
        }
        stmt = pg_insert(AbsenteeBallotApplication).values(**absentee_data_2)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "county": stmt.excluded.county,
                "voter_registration_number": stmt.excluded.voter_registration_number,
                "application_status": stmt.excluded.application_status,
                "ballot_status": stmt.excluded.ballot_status,
                "import_job_id": stmt.excluded.import_job_id,
            },
        )
        await session.execute(stmt)

        await session.commit()

    yield

    # Cleanup: remove seeded rows so the DB is left clean.
    async with factory() as session:
        await session.execute(
            delete(AbsenteeBallotApplication).where(
                AbsenteeBallotApplication.id.in_([ABSENTEE_RECORD_ID, ABSENTEE_RECORD_ID_2])
            )
        )
        await session.execute(delete(VoterHistory).where(VoterHistory.id == VOTER_HISTORY_ID))
        await session.execute(delete(UserInvite).where(UserInvite.id == INVITE_ID))
        await session.execute(delete(TOTPCredential).where(TOTPCredential.user_id == TOTP_USER_ID))
        await session.execute(delete(ElectedOfficial).where(ElectedOfficial.id == OFFICIAL_ID))
        await session.execute(delete(Voter).where(Voter.id == VOTER_ID))
        await session.execute(delete(Boundary).where(Boundary.id == BOUNDARY_ID))
        await session.execute(delete(ImportJob).where(ImportJob.id == IMPORT_JOB_ID))
        await session.execute(delete(CandidateLink).where(CandidateLink.id == CANDIDATE_LINK_ID))
        await session.execute(delete(Candidate).where(Candidate.id == CANDIDATE_ID))
        await session.execute(delete(Election).where(Election.id == ELECTION_ID))
        await session.execute(
            delete(User).where(User.id.in_([ADMIN_USER_ID, ANALYST_USER_ID, VIEWER_USER_ID, TOTP_USER_ID]))
        )
        await session.commit()


@pytest.fixture(scope="session", autouse=True)
def mock_mailer() -> Generator[MagicMock]:
    """Mock MailgunMailer for the entire E2E session to prevent real email delivery.

    Patches the factory function used by auth route handlers so no request
    ever reaches the Mailgun API during E2E tests.
    """
    mock = MagicMock()
    mock.send_template = AsyncMock(return_value=None)
    mock.send_email = AsyncMock(return_value=None)
    with patch("voter_api.api.v1.auth._get_mailer", return_value=mock):
        yield mock
