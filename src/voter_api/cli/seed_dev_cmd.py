"""CLI command for seeding lightweight dev data into the database.

The ``voter-api db seed-dev`` command inserts a minimal set of realistic
records (users, elections, boundaries, voters, etc.) using idempotent
``INSERT ... ON CONFLICT DO UPDATE`` statements.  Safe to run repeatedly.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date

from loguru import logger
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from voter_api.core.database import dispose_engine, get_engine, init_engine
from voter_api.core.security import hash_password
from voter_api.models.boundary import Boundary
from voter_api.models.candidate import Candidate
from voter_api.models.elected_official import ElectedOfficial
from voter_api.models.election import Election
from voter_api.models.import_job import ImportJob
from voter_api.models.user import User
from voter_api.models.voter import Voter
from voter_api.models.voter_history import VoterHistory

# ---------------------------------------------------------------------------
# Deterministic UUIDs in the 11111111-xxxx range (avoids E2E's 00000000-xxxx)
# ---------------------------------------------------------------------------
ADMIN_USER_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")
ANALYST_USER_ID = uuid.UUID("11111111-0000-0000-0000-000000000002")
VIEWER_USER_ID = uuid.UUID("11111111-0000-0000-0000-000000000003")

ELECTION_GENERAL_ID = uuid.UUID("11111111-0000-0000-0000-000000000010")
ELECTION_PRIMARY_ID = uuid.UUID("11111111-0000-0000-0000-000000000011")

BOUNDARY_CONGRESSIONAL_ID = uuid.UUID("11111111-0000-0000-0000-000000000030")
BOUNDARY_STATE_SENATE_ID = uuid.UUID("11111111-0000-0000-0000-000000000031")
BOUNDARY_COUNTY_ID = uuid.UUID("11111111-0000-0000-0000-000000000032")

VOTER_IDS = [uuid.UUID(f"11111111-0000-0000-0000-00000000005{i}") for i in range(5)]

IMPORT_JOB_ID = uuid.UUID("11111111-0000-0000-0000-000000000060")
VOTER_HISTORY_IDS = [uuid.UUID(f"11111111-0000-0000-0000-00000000006{i}") for i in range(1, 4)]

OFFICIAL_IDS = [
    uuid.UUID("11111111-0000-0000-0000-000000000020"),
    uuid.UUID("11111111-0000-0000-0000-000000000021"),
]

CANDIDATE_IDS = [
    uuid.UUID("11111111-0000-0000-0000-000000000070"),
    uuid.UUID("11111111-0000-0000-0000-000000000071"),
]

DEV_PASSWORD = "Dev-Password-2024!"  # noqa: S105


async def _seed() -> None:
    """Insert dev seed data using idempotent upserts."""
    from voter_api.core.config import get_settings

    settings = get_settings()
    init_engine(settings.database_url, schema=settings.database_schema)
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            hashed = hash_password(DEV_PASSWORD)

            # --- Users --------------------------------------------------------
            users = [
                {
                    "id": ADMIN_USER_ID,
                    "username": "dev_admin",
                    "email": "dev_admin@localhost",
                    "hashed_password": hashed,
                    "role": "admin",
                    "is_active": True,
                },
                {
                    "id": ANALYST_USER_ID,
                    "username": "dev_analyst",
                    "email": "dev_analyst@localhost",
                    "hashed_password": hashed,
                    "role": "analyst",
                    "is_active": True,
                },
                {
                    "id": VIEWER_USER_ID,
                    "username": "dev_viewer",
                    "email": "dev_viewer@localhost",
                    "hashed_password": hashed,
                    "role": "viewer",
                    "is_active": True,
                },
            ]
            for user_data in users:
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
            logger.info("Seeded 3 dev users (dev_admin / dev_analyst / dev_viewer)")

            # --- Elections ----------------------------------------------------
            elections = [
                {
                    "id": ELECTION_GENERAL_ID,
                    "name": "2024 General Election",
                    "election_date": date(2024, 11, 5),
                    "election_type": "general",
                    "district": "Statewide",
                    "status": "finalized",
                },
                {
                    "id": ELECTION_PRIMARY_ID,
                    "name": "2024 Primary Election",
                    "election_date": date(2024, 5, 21),
                    "election_type": "primary",
                    "district": "Statewide",
                    "status": "finalized",
                },
            ]
            for election_data in elections:
                stmt = pg_insert(Election).values(**election_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "name": stmt.excluded.name,
                        "election_date": stmt.excluded.election_date,
                        "election_type": stmt.excluded.election_type,
                        "district": stmt.excluded.district,
                        "status": stmt.excluded.status,
                    },
                )
                await session.execute(stmt)
            logger.info("Seeded 2 elections")

            # --- Boundaries ---------------------------------------------------
            # Simple polygons in the Atlanta metro area (real-ish GA coordinates)
            boundaries = [
                {
                    "id": BOUNDARY_CONGRESSIONAL_ID,
                    "name": "Georgia Congressional District 5",
                    "boundary_type": "congressional",
                    "boundary_identifier": "005",
                    "geometry": func.ST_GeomFromText(
                        "MULTIPOLYGON(((-84.45 33.70, -84.30 33.70, -84.30 33.82, -84.45 33.82, -84.45 33.70)))",
                        4326,
                    ),
                    "properties": {"district_number": "5"},
                    "source": "dev-seed",
                },
                {
                    "id": BOUNDARY_STATE_SENATE_ID,
                    "name": "Georgia State Senate District 36",
                    "boundary_type": "state_senate",
                    "boundary_identifier": "036",
                    "geometry": func.ST_GeomFromText(
                        "MULTIPOLYGON(((-84.42 33.72, -84.32 33.72, -84.32 33.80, -84.42 33.80, -84.42 33.72)))",
                        4326,
                    ),
                    "properties": {"district_number": "36"},
                    "source": "dev-seed",
                },
                {
                    "id": BOUNDARY_COUNTY_ID,
                    "name": "Fulton County",
                    "boundary_type": "county",
                    "boundary_identifier": "FULTON",
                    "geometry": func.ST_GeomFromText(
                        "MULTIPOLYGON(((-84.50 33.65, -84.25 33.65, -84.25 33.90, -84.50 33.90, -84.50 33.65)))",
                        4326,
                    ),
                    "properties": {"county_name": "Fulton"},
                    "source": "dev-seed",
                },
            ]
            for boundary_data in boundaries:
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
            logger.info("Seeded 3 boundaries")

            # --- Voters -------------------------------------------------------
            voter_records = [
                {
                    "id": VOTER_IDS[0],
                    "county": "FULTON",
                    "voter_registration_number": "DEV000001",
                    "status": "A",
                    "last_name": "JOHNSON",
                    "first_name": "ALICE",
                    "congressional_district": "005",
                    "residence_street_number": "200",
                    "residence_street_name": "PEACHTREE",
                    "residence_street_type": "ST",
                    "residence_city": "ATLANTA",
                    "residence_zipcode": "30303",
                    "official_latitude": 33.75,
                    "official_longitude": -84.38,
                    "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.38, 33.75), 4326),
                    "official_source": "dev-seed",
                },
                {
                    "id": VOTER_IDS[1],
                    "county": "FULTON",
                    "voter_registration_number": "DEV000002",
                    "status": "A",
                    "last_name": "SMITH",
                    "first_name": "BOB",
                    "congressional_district": "005",
                    "residence_street_number": "300",
                    "residence_street_name": "SPRING",
                    "residence_street_type": "ST",
                    "residence_city": "ATLANTA",
                    "residence_zipcode": "30308",
                    "official_latitude": 33.77,
                    "official_longitude": -84.38,
                    "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.38, 33.77), 4326),
                    "official_source": "dev-seed",
                },
                {
                    "id": VOTER_IDS[2],
                    "county": "FULTON",
                    "voter_registration_number": "DEV000003",
                    "status": "A",
                    "last_name": "WILLIAMS",
                    "first_name": "CAROL",
                    "congressional_district": "005",
                    "residence_street_number": "400",
                    "residence_street_name": "FORSYTH",
                    "residence_street_type": "ST",
                    "residence_city": "ATLANTA",
                    "residence_zipcode": "30303",
                    "official_latitude": 33.76,
                    "official_longitude": -84.39,
                    "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.39, 33.76), 4326),
                    "official_source": "dev-seed",
                },
                {
                    "id": VOTER_IDS[3],
                    "county": "FULTON",
                    "voter_registration_number": "DEV000004",
                    "status": "A",
                    "last_name": "DAVIS",
                    "first_name": "DEREK",
                    "congressional_district": "005",
                    "residence_street_number": "500",
                    "residence_street_name": "MARIETTA",
                    "residence_street_type": "ST",
                    "residence_city": "ATLANTA",
                    "residence_zipcode": "30313",
                    "official_latitude": 33.76,
                    "official_longitude": -84.40,
                    "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.40, 33.76), 4326),
                    "official_source": "dev-seed",
                },
                {
                    "id": VOTER_IDS[4],
                    "county": "FULTON",
                    "voter_registration_number": "DEV000005",
                    "status": "I",
                    "last_name": "EVANS",
                    "first_name": "EVE",
                    "congressional_district": "005",
                    "residence_street_number": "600",
                    "residence_street_name": "LUCKIE",
                    "residence_street_type": "ST",
                    "residence_city": "ATLANTA",
                    "residence_zipcode": "30313",
                    "official_latitude": 33.76,
                    "official_longitude": -84.39,
                    "official_point": func.ST_SetSRID(func.ST_MakePoint(-84.39, 33.76), 4326),
                    "official_source": "dev-seed",
                },
            ]
            for voter_data in voter_records:
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
            logger.info("Seeded 5 voters")

            # --- Import Job (FK for voter history) ----------------------------
            import_job_data = {
                "id": IMPORT_JOB_ID,
                "file_name": "dev_seed_history.csv",
                "file_type": "voter_history",
                "status": "completed",
                "total_records": 3,
                "records_succeeded": 3,
                "records_failed": 0,
                "records_inserted": 3,
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
            logger.info("Seeded 1 import job")

            # --- Voter History ------------------------------------------------
            history_records = [
                {
                    "id": VOTER_HISTORY_IDS[0],
                    "voter_registration_number": "DEV000001",
                    "county": "FULTON",
                    "election_date": date(2024, 11, 5),
                    "election_type": "General Election",
                    "normalized_election_type": "general",
                    "party": None,
                    "ballot_style": "FULTON-01",
                    "absentee": False,
                    "provisional": False,
                    "supplemental": False,
                    "election_id": ELECTION_GENERAL_ID,
                    "import_job_id": IMPORT_JOB_ID,
                },
                {
                    "id": VOTER_HISTORY_IDS[1],
                    "voter_registration_number": "DEV000002",
                    "county": "FULTON",
                    "election_date": date(2024, 11, 5),
                    "election_type": "General Election",
                    "normalized_election_type": "general",
                    "party": None,
                    "ballot_style": "FULTON-01",
                    "absentee": True,
                    "provisional": False,
                    "supplemental": False,
                    "election_id": ELECTION_GENERAL_ID,
                    "import_job_id": IMPORT_JOB_ID,
                },
                {
                    "id": VOTER_HISTORY_IDS[2],
                    "voter_registration_number": "DEV000001",
                    "county": "FULTON",
                    "election_date": date(2024, 5, 21),
                    "election_type": "Primary Election",
                    "normalized_election_type": "primary",
                    "party": "D",
                    "ballot_style": "FULTON-01",
                    "absentee": False,
                    "provisional": False,
                    "supplemental": False,
                    "election_id": ELECTION_PRIMARY_ID,
                    "import_job_id": IMPORT_JOB_ID,
                },
            ]
            for history_data in history_records:
                stmt = pg_insert(VoterHistory).values(**history_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "county": stmt.excluded.county,
                        "election_id": stmt.excluded.election_id,
                        "import_job_id": stmt.excluded.import_job_id,
                    },
                )
                await session.execute(stmt)
            logger.info("Seeded 3 voter history records")

            # --- Elected Officials --------------------------------------------
            officials = [
                {
                    "id": OFFICIAL_IDS[0],
                    "boundary_type": "congressional",
                    "district_identifier": "005",
                    "full_name": "Nikema Williams",
                    "first_name": "Nikema",
                    "last_name": "Williams",
                    "party": "Democratic",
                    "title": "Representative",
                    "status": "approved",
                },
                {
                    "id": OFFICIAL_IDS[1],
                    "boundary_type": "state_senate",
                    "district_identifier": "036",
                    "full_name": "Nan Orrock",
                    "first_name": "Nan",
                    "last_name": "Orrock",
                    "party": "Democratic",
                    "title": "Senator",
                    "status": "approved",
                },
            ]
            for official_data in officials:
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
            logger.info("Seeded 2 elected officials")

            # --- Candidates ---------------------------------------------------
            candidates = [
                {
                    "id": CANDIDATE_IDS[0],
                    "election_id": ELECTION_GENERAL_ID,
                    "full_name": "Alice Johnson",
                    "party": "Democratic",
                    "filing_status": "qualified",
                    "is_incumbent": True,
                    "ballot_order": 1,
                },
                {
                    "id": CANDIDATE_IDS[1],
                    "election_id": ELECTION_PRIMARY_ID,
                    "full_name": "Bob Smith",
                    "party": "Republican",
                    "filing_status": "qualified",
                    "is_incumbent": False,
                    "ballot_order": 1,
                },
            ]
            for candidate_data in candidates:
                stmt = pg_insert(Candidate).values(**candidate_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "election_id": stmt.excluded.election_id,
                        "full_name": stmt.excluded.full_name,
                        "party": stmt.excluded.party,
                        "filing_status": stmt.excluded.filing_status,
                        "is_incumbent": stmt.excluded.is_incumbent,
                        "ballot_order": stmt.excluded.ballot_order,
                    },
                )
                await session.execute(stmt)
            logger.info("Seeded 2 candidates")

            await session.commit()
            logger.success("Dev seed data complete")
    finally:
        await dispose_engine()


def _is_dev_environment() -> bool:
    """Check whether the current environment is safe for dev seeding.

    Returns True when any of these conditions hold:
    - ENV or ENVIRONMENT is set to "development", "dev", or "test"
    - DATABASE_URL points to localhost / 127.0.0.1 / a docker-compose service name
    """
    env = os.environ.get("ENV", os.environ.get("ENVIRONMENT", "")).lower()
    if env in {"development", "dev", "test"}:
        return True

    db_url = os.environ.get("DATABASE_URL", "")
    return any(host in db_url for host in ("localhost", "127.0.0.1", "db:"))


def seed_dev() -> None:
    """Seed lightweight dev data (users, elections, boundaries, voters).

    Idempotent — safe to run multiple times.  All records use deterministic
    UUIDs in the 11111111-xxxx range to avoid collision with E2E test data.

    Login credentials:
      dev_admin / Dev-Password-2024!
      dev_analyst / Dev-Password-2024!
      dev_viewer / Dev-Password-2024!
    """
    if not _is_dev_environment():
        logger.error(
            "seed-dev is blocked outside development environments. "
            "Set ENV=development or use a local DATABASE_URL to proceed."
        )
        raise SystemExit(1)
    asyncio.run(_seed())
