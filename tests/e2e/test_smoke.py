"""End-to-end smoke tests against a real PostGIS database.

Each test class covers one API router.  Tests use the real FastAPI app
(via ASGI transport) and a real database that has been migrated and seeded
by the ``seed_database`` session fixture.
"""

import uuid

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from tests.e2e.conftest import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    BOUNDARY_ID,
    ELECTION_ID,
    OFFICIAL_ID,
)
from voter_api.models.election import Election
from voter_api.models.user import User

# All E2E tests and their fixtures share a single session-scoped event loop.
# This must live in the test module (not conftest.py) for pytest-asyncio to
# pick it up for collected tests.
pytestmark = pytest.mark.asyncio(loop_scope="session")

PREFIX = "/api/v1"


# ── Helpers ────────────────────────────────────────────────────────────────


def _url(path: str) -> str:
    return f"{PREFIX}{path}"


# ── Health ─────────────────────────────────────────────────────────────────


class TestHealth:
    """GET /api/v1/health and /api/v1/info — no auth required."""

    async def test_health_returns_200(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/health"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"

    async def test_info_returns_version(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/info"))
        assert resp.status_code == 200
        body = resp.json()
        assert "version" in body
        assert "environment" in body


# ── Auth ───────────────────────────────────────────────────────────────────


class TestAuth:
    """Auth endpoints: login, refresh, /auth/me, user CRUD."""

    async def test_login_returns_tokens(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            _url("/auth/login"),
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_bad_password_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            _url("/auth/login"),
            data={"username": ADMIN_USERNAME, "password": "wrong-password"},
        )
        assert resp.status_code == 401

    async def test_refresh_token(self, client: httpx.AsyncClient) -> None:
        # First login to get tokens.
        login_resp = await client.post(
            _url("/auth/login"),
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        refresh_token = login_resp.json()["refresh_token"]

        resp = await client.post(
            _url("/auth/refresh"),
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_get_me(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/auth/me"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == ADMIN_USERNAME
        assert body["role"] == "admin"

    async def test_get_me_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/auth/me"))
        assert resp.status_code == 401

    async def test_list_users_admin(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/users"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body
        assert body["pagination"]["total"] >= 3  # seeded users

    async def test_list_users_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url("/users"))
        assert resp.status_code == 403

    async def test_create_and_list_user(self, admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
        new_user = {
            "username": f"e2e_tmp_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_tmp_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        resp = await admin_client.post(_url("/users"), json=new_user)
        # Parse response before the try block so user_id is available for
        # cleanup in finally even if an assertion fails after the resource was
        # created (e.g., status is 201 but a later assert raises).
        body = resp.json() if resp.status_code == 201 else {}
        user_id: str | None = body.get("id")
        try:
            assert resp.status_code == 201
            assert user_id is not None
            assert body["username"] == new_user["username"]
            assert body["role"] == "viewer"

            # Verify the new user appears in the list.
            list_resp = await admin_client.get(_url("/users"))
            assert list_resp.status_code == 200
            list_body = list_resp.json()
            assert "items" in list_body
            user_ids = [u["id"] for u in list_body["items"]]
            assert user_id in user_ids
        finally:
            # Cleanup: no DELETE /users endpoint, so remove via DB directly.
            # Runs even if assertions fail to keep the DB idempotent.
            if user_id is not None:
                await db_session.execute(delete(User).where(User.id == uuid.UUID(user_id)))
                await db_session.commit()


# ── Boundaries ─────────────────────────────────────────────────────────────


class TestBoundaries:
    """Boundary endpoints — all public (no auth)."""

    async def test_list_boundaries(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/boundaries"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_list_boundaries_filter_by_type(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/boundaries"), params={"boundary_type": "congressional"})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert all(b["boundary_type"] == "congressional" for b in items)

    async def test_get_boundary_detail(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/boundaries/{BOUNDARY_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(BOUNDARY_ID)
        assert body["boundary_type"] == "congressional"

    async def test_get_boundary_not_found(self, client: httpx.AsyncClient) -> None:
        fake_id = uuid.uuid4()
        resp = await client.get(_url(f"/boundaries/{fake_id}"))
        assert resp.status_code == 404

    async def test_list_boundary_types(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/boundaries/types"))
        assert resp.status_code == 200
        body = resp.json()
        assert "types" in body
        assert "congressional" in body["types"]

    async def test_containing_point(self, client: httpx.AsyncClient) -> None:
        """Point inside the seeded congressional polygon."""
        resp = await client.get(
            _url("/boundaries/containing-point"),
            params={"latitude": 33.75, "longitude": -84.35},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # The seeded polygon covers this point.
        ids = [b["id"] for b in body]
        assert str(BOUNDARY_ID) in ids


# ── Elections ──────────────────────────────────────────────────────────────


class TestElections:
    """Election endpoints — public reads, admin writes."""

    async def test_list_elections(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/elections"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) >= 1

    async def test_get_election_detail(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elections/{ELECTION_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(ELECTION_ID)
        assert body["name"] == "E2E Test General Election"

    async def test_get_election_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elections/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_create_election_requires_admin(self, viewer_client: httpx.AsyncClient) -> None:
        payload = {
            "name": "Forbidden Election",
            "election_date": "2025-01-01",
            "election_type": "primary",
            "district": "Statewide",
            "data_source_url": "https://results.enr.clarityelections.com/GA/test2/json",
        }
        resp = await viewer_client.post(_url("/elections"), json=payload)
        assert resp.status_code == 403

    async def test_create_and_read_election(self, admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
        payload = {
            "name": f"E2E Temp Election {uuid.uuid4().hex[:8]}",
            "election_date": "2025-06-15",
            "election_type": "runoff",
            "district": "Statewide",
            "data_source_url": "https://results.enr.clarityelections.com/GA/temp/json",
            "refresh_interval_seconds": 120,
        }
        create_resp = await admin_client.post(_url("/elections"), json=payload)
        # Parse response before the try block so election_id is available for
        # cleanup in finally even if an assertion fails after the resource was
        # created (e.g., status is 201 but a later assert raises).
        election_id: str | None = create_resp.json().get("id") if create_resp.status_code == 201 else None
        try:
            assert create_resp.status_code == 201
            assert election_id is not None

            detail_resp = await admin_client.get(_url(f"/elections/{election_id}"))
            assert detail_resp.status_code == 200
            assert detail_resp.json()["name"] == payload["name"]
        finally:
            # Cleanup: no DELETE /elections endpoint, so remove via DB directly.
            # Runs even if assertions fail to keep the DB idempotent.
            if election_id is not None:
                await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
                await db_session.commit()

    async def test_get_election_results_empty(self, client: httpx.AsyncClient) -> None:
        """Results endpoint returns 200 with empty data when no results ingested yet."""
        resp = await client.get(_url(f"/elections/{ELECTION_ID}/results"))
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


# ── Elected Officials ─────────────────────────────────────────────────────


class TestElectedOfficials:
    """Elected official endpoints — public reads, admin writes."""

    async def test_list_officials(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/elected-officials"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert len(body["items"]) >= 1

    async def test_get_official_detail(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elected-officials/{OFFICIAL_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["full_name"] == "Jane E2E Doe"
        assert body["boundary_type"] == "congressional"

    async def test_get_official_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elected-officials/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_list_by_district(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(
            _url("/elected-officials/by-district"),
            params={"boundary_type": "congressional", "district_identifier": "1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert any(o["full_name"] == "Jane E2E Doe" for o in body)

    async def test_create_official_requires_admin(self, viewer_client: httpx.AsyncClient) -> None:
        payload = {
            "boundary_type": "congressional",
            "district_identifier": "99",
            "full_name": "Forbidden Official",
        }
        resp = await viewer_client.post(_url("/elected-officials"), json=payload)
        assert resp.status_code == 403

    async def test_crud_lifecycle(self, admin_client: httpx.AsyncClient) -> None:
        """Create -> read -> update -> approve -> delete an elected official.

        Each run uses a UUID-derived ``unique`` suffix, making collisions
        effectively impossible even on rapid-retry or parallel runs against a
        shared database.  Cleanup is wrapped in try/finally so the resource is
        deleted even if a mid-test assertion fails.
        """
        unique = uuid.uuid4().hex[:8]

        # Create
        create_payload = {
            "boundary_type": "state_house",
            "district_identifier": unique,
            "full_name": f"E2E Official {unique}",
            "party": "Independent",
            "title": "Representative",
        }
        create_resp = await admin_client.post(_url("/elected-officials"), json=create_payload)
        # Extract the ID before try so cleanup works even if a later assert fails.
        official_id: str | None = create_resp.json().get("id") if create_resp.status_code == 201 else None
        try:
            assert create_resp.status_code == 201
            assert official_id is not None

            # Read
            get_resp = await admin_client.get(_url(f"/elected-officials/{official_id}"))
            assert get_resp.status_code == 200
            assert get_resp.json()["full_name"] == create_payload["full_name"]

            # Update
            update_resp = await admin_client.patch(
                _url(f"/elected-officials/{official_id}"),
                json={"party": "Nonpartisan"},
            )
            assert update_resp.status_code == 200
            assert update_resp.json()["party"] == "Nonpartisan"

            # Approve
            approve_resp = await admin_client.post(
                _url(f"/elected-officials/{official_id}/approve"),
                json={},
            )
            assert approve_resp.status_code == 200
            assert approve_resp.json()["status"] == "approved"

            # Delete
            delete_resp = await admin_client.delete(_url(f"/elected-officials/{official_id}"))
            assert delete_resp.status_code == 204

            # Verify gone
            gone_resp = await admin_client.get(_url(f"/elected-officials/{official_id}"))
            assert gone_resp.status_code == 404
        finally:
            # Cleanup: delete via API if still present (runs even if assertions fail).
            if official_id is not None:
                await admin_client.delete(_url(f"/elected-officials/{official_id}"))

    async def test_get_official_sources(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elected-officials/{OFFICIAL_ID}/sources"))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ── Voters ─────────────────────────────────────────────────────────────────


class TestVoters:
    """Voter endpoints — authenticated reads."""

    async def test_search_voters_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/voters"))
        assert resp.status_code == 401

    async def test_search_voters_empty(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/voters"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_voter_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url(f"/voters/{uuid.uuid4()}"))
        assert resp.status_code == 404


# ── Geocoding ──────────────────────────────────────────────────────────────


class TestGeocoding:
    """Geocoding endpoints — public reads; admin writes."""

    async def test_geocode_is_public(self, client: httpx.AsyncClient) -> None:
        """Geocode endpoint is public — no auth required.

        Acceptable statuses: 200 (geocoded), 404 (no match), 502 (provider down).
        """
        resp = await client.get(_url("/geocoding/geocode"), params={"address": "100 Peachtree St"})
        assert resp.status_code in {200, 404, 502}
        if resp.status_code == 200:
            body = resp.json()
            assert "formatted_address" in body

    async def test_verify_is_public(self, client: httpx.AsyncClient) -> None:
        """Verify endpoint is public — no auth required.

        Acceptable statuses: 200 (verified), 502 (provider down).
        """
        resp = await client.get(_url("/geocoding/verify"), params={"address": "100 Peachtree St"})
        assert resp.status_code in {200, 502}
        if resp.status_code == 200:
            body = resp.json()
            assert "input_address" in body
            assert "is_well_formed" in body

    async def test_point_lookup_is_public(self, client: httpx.AsyncClient) -> None:
        """Point lookup endpoint is public and DB-backed — no external provider."""
        resp = await client.get(
            _url("/geocoding/point-lookup"),
            params={"lat": 33.75, "lng": -84.39},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "districts" in body
        assert isinstance(body["districts"], list)

    async def test_cache_stats_requires_auth(self, client: httpx.AsyncClient) -> None:
        """Cache stats endpoint requires authentication (any role)."""
        resp = await client.get(_url("/geocoding/cache/stats"))
        assert resp.status_code == 401

    async def test_providers_list_is_public(self, client: httpx.AsyncClient) -> None:
        """Providers list endpoint is public — returns provider info and fallback order."""
        resp = await client.get(_url("/geocoding/providers"))
        assert resp.status_code == 200
        body = resp.json()
        assert "providers" in body
        assert "fallback_order" in body
        assert isinstance(body["providers"], list)
        assert len(body["providers"]) >= 1
        # Census should always be present
        names = [p["name"] for p in body["providers"]]
        assert "census" in names
        # Each provider should have expected fields
        for p in body["providers"]:
            assert "name" in p
            assert "service_type" in p
            assert "requires_api_key" in p
            assert "is_configured" in p

    async def test_batch_accepts_provider_string(self, admin_client: httpx.AsyncClient) -> None:
        """Batch endpoint accepts any provider string (not just 'census')."""
        resp = await admin_client.post(
            _url("/geocoding/batch"),
            json={"provider": "census", "fallback": False},
        )
        assert resp.status_code == 202

    async def test_batch_fallback_enabled(self, admin_client: httpx.AsyncClient) -> None:
        """Batch endpoint accepts fallback=True and returns 202 Accepted."""
        resp = await admin_client.post(
            _url("/geocoding/batch"),
            json={"provider": "census", "fallback": True},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert "id" in body
        assert body["status"] == "pending"


# ── Imports ────────────────────────────────────────────────────────────────


class TestImports:
    """Import endpoints — admin only."""

    async def test_list_imports_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/imports"))
        assert resp.status_code == 401

    async def test_list_imports_admin(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/imports"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    async def test_list_imports_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url("/imports"))
        assert resp.status_code == 403


# ── Exports ────────────────────────────────────────────────────────────────


class TestExports:
    """Export endpoints — authenticated access."""

    async def test_list_exports_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/exports"))
        assert resp.status_code == 401

    async def test_list_exports(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/exports"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body


# ── Analysis ───────────────────────────────────────────────────────────────


class TestAnalysis:
    """Analysis endpoints — admin/analyst access."""

    async def test_list_runs_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/analysis/runs"))
        assert resp.status_code == 401

    async def test_list_runs(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url("/analysis/runs"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    async def test_list_runs_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url("/analysis/runs"))
        assert resp.status_code == 403


# ── Datasets ───────────────────────────────────────────────────────────────


class TestDatasets:
    """Datasets endpoint — public, no auth."""

    async def test_list_datasets(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/datasets"))
        assert resp.status_code == 200


# ── Pagination ─────────────────────────────────────────────────────────────


class TestPagination:
    """Verify pagination parameters are respected across list endpoints."""

    @pytest.mark.parametrize(
        "endpoint",
        [
            "/boundaries",
            "/elections",
            "/elected-officials",
        ],
    )
    async def test_pagination_params(self, client: httpx.AsyncClient, endpoint: str) -> None:
        resp = await client.get(_url(endpoint), params={"page": 1, "page_size": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 1

    async def test_invalid_page_size(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/boundaries"), params={"page_size": 0})
        assert resp.status_code == 422


# ── Cross-cutting: RBAC ───────────────────────────────────────────────────


class TestRBAC:
    """Role-based access control smoke tests across routers."""

    async def test_admin_can_access_users(self, admin_client: httpx.AsyncClient) -> None:
        assert (await admin_client.get(_url("/users"))).status_code == 200

    async def test_analyst_cannot_access_users(self, analyst_client: httpx.AsyncClient) -> None:
        assert (await analyst_client.get(_url("/users"))).status_code == 403

    async def test_viewer_cannot_access_users(self, viewer_client: httpx.AsyncClient) -> None:
        assert (await viewer_client.get(_url("/users"))).status_code == 403

    async def test_analyst_can_access_analysis(self, analyst_client: httpx.AsyncClient) -> None:
        assert (await analyst_client.get(_url("/analysis/runs"))).status_code == 200

    async def test_viewer_cannot_access_analysis(self, viewer_client: httpx.AsyncClient) -> None:
        assert (await viewer_client.get(_url("/analysis/runs"))).status_code == 403

    async def test_viewer_can_read_voters(self, viewer_client: httpx.AsyncClient) -> None:
        assert (await viewer_client.get(_url("/voters"))).status_code == 200


# ── Voter History ──────────────────────────────────────────────────────────


class TestVoterHistory:
    """Smoke tests for the voter_history router (analyst/admin only)."""

    async def test_voter_history_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url("/voters/FAKE123/history"))
        assert resp.status_code == 401

    async def test_voter_history_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url("/voters/FAKE123/history"))
        assert resp.status_code == 403

    async def test_analyst_can_access_voter_history(self, analyst_client: httpx.AsyncClient) -> None:
        """Analyst role bypasses RBAC — endpoint returns 200/404, not 401/403."""
        resp = await analyst_client.get(_url("/voters/FAKE123/history"))
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert "items" in resp.json()

    async def test_election_participation_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elections/{ELECTION_ID}/participation"))
        assert resp.status_code == 401

    async def test_election_participation_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url(f"/elections/{ELECTION_ID}/participation"))
        assert resp.status_code == 403

    async def test_election_participation_stats_accessible_to_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        """Stats endpoint requires only authentication — viewer role is sufficient."""
        resp = await viewer_client.get(_url(f"/elections/{ELECTION_ID}/participation/stats"))
        assert resp.status_code == 200
        body = resp.json()
        assert "election_id" in body
