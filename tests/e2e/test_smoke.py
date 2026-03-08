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
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ADMIN_USER_ID,
    ADMIN_USERNAME,
    BOUNDARY_ID,
    CANDIDATE_ID,
    ELECTION_ID,
    INVITE_ID,
    OFFICIAL_ID,
    TOTP_USER_ID,
    TOTP_USERNAME,
    VOTER_ID,
)
from voter_api.models.auth_tokens import UserInvite
from voter_api.models.election import Election

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
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_bad_password_returns_401(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            _url("/auth/login"),
            json={"username": ADMIN_USERNAME, "password": "wrong-password"},
        )
        assert resp.status_code == 401

    async def test_refresh_token(self, client: httpx.AsyncClient) -> None:
        # First login to get tokens.
        login_resp = await client.post(
            _url("/auth/login"),
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
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

    async def test_create_and_list_user(self, admin_client: httpx.AsyncClient) -> None:
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
            # Cleanup via DELETE endpoint now available.
            if user_id is not None:
                cleanup = await admin_client.delete(_url(f"/users/{user_id}"))
                assert cleanup.status_code in (204, 404)

    async def test_get_user_by_id(self, admin_client: httpx.AsyncClient) -> None:
        new_user = {
            "username": f"e2e_get_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_get_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        create_resp = await admin_client.post(_url("/users"), json=new_user)
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]
        try:
            resp = await admin_client.get(_url(f"/users/{user_id}"))
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == user_id
            assert body["username"] == new_user["username"]
            assert body["role"] == "viewer"
        finally:
            cleanup = await admin_client.delete(_url(f"/users/{user_id}"))
            assert cleanup.status_code in (204, 404)

    async def test_get_user_by_id_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url(f"/users/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_patch_user_email_and_role(self, admin_client: httpx.AsyncClient) -> None:
        new_user = {
            "username": f"e2e_patch_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_patch_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        create_resp = await admin_client.post(_url("/users"), json=new_user)
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]
        try:
            new_email = f"e2e_patched_{uuid.uuid4().hex[:8]}@test.com"
            patch_resp = await admin_client.patch(
                _url(f"/users/{user_id}"),
                json={"email": new_email, "role": "analyst"},
            )
            assert patch_resp.status_code == 200
            body = patch_resp.json()
            assert body["email"] == new_email
            assert body["role"] == "analyst"
            # Username unchanged
            assert body["username"] == new_user["username"]
        finally:
            cleanup = await admin_client.delete(_url(f"/users/{user_id}"))
            assert cleanup.status_code in (204, 404)

    async def test_patch_user_suspend(self, admin_client: httpx.AsyncClient) -> None:
        new_user = {
            "username": f"e2e_suspend_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_suspend_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        create_resp = await admin_client.post(_url("/users"), json=new_user)
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]
        try:
            patch_resp = await admin_client.patch(
                _url(f"/users/{user_id}"),
                json={"is_active": False},
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["is_active"] is False
        finally:
            cleanup = await admin_client.delete(_url(f"/users/{user_id}"))
            assert cleanup.status_code in (204, 404)

    async def test_patch_user_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.patch(_url(f"/users/{uuid.uuid4()}"), json={"role": "analyst"})
        assert resp.status_code == 404

    async def test_patch_user_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.patch(_url(f"/users/{uuid.uuid4()}"), json={"role": "analyst"})
        assert resp.status_code == 403

    async def test_delete_user(self, admin_client: httpx.AsyncClient) -> None:
        new_user = {
            "username": f"e2e_del_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_del_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        create_resp = await admin_client.post(_url("/users"), json=new_user)
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        delete_resp = await admin_client.delete(_url(f"/users/{user_id}"))
        assert delete_resp.status_code == 204

        # Verify the user is gone
        get_resp = await admin_client.get(_url(f"/users/{user_id}"))
        assert get_resp.status_code == 404

    async def test_delete_user_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.delete(_url(f"/users/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_delete_user_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.delete(_url(f"/users/{uuid.uuid4()}"))
        assert resp.status_code == 403

    async def test_get_user_by_id_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/users/{uuid.uuid4()}"))
        assert resp.status_code == 401

    async def test_patch_user_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(_url(f"/users/{uuid.uuid4()}"), json={"role": "analyst"})
        assert resp.status_code == 401

    async def test_delete_user_unauthenticated(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete(_url(f"/users/{uuid.uuid4()}"))
        assert resp.status_code == 401

    async def test_delete_self_returns_400(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.delete(_url(f"/users/{ADMIN_USER_ID}"))
        assert resp.status_code == 400
        assert "own account" in resp.json()["detail"]

    async def test_patch_self_deactivate_returns_400(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.patch(
            _url(f"/users/{ADMIN_USER_ID}"),
            json={"is_active": False},
        )
        assert resp.status_code == 400
        assert "Cannot deactivate your own account" in resp.json()["detail"]

    async def test_patch_self_downgrade_returns_400(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.patch(
            _url(f"/users/{ADMIN_USER_ID}"),
            json={"role": "viewer"},
        )
        assert resp.status_code == 400
        assert "Cannot downgrade your own admin role" in resp.json()["detail"]

    async def test_get_user_by_id_forbidden_for_viewer(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.get(_url(f"/users/{ADMIN_USER_ID}"))
        assert resp.status_code == 403

    async def test_patch_user_email_conflict_returns_409(self, admin_client: httpx.AsyncClient) -> None:
        user_a = {
            "username": f"e2e_ca_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_ca_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        user_b = {
            "username": f"e2e_cb_{uuid.uuid4().hex[:8]}",
            "email": f"e2e_cb_{uuid.uuid4().hex[:8]}@test.com",
            "password": "strongpassword123",
            "role": "viewer",
        }
        id_a: str | None = None
        id_b: str | None = None
        try:
            create_a = await admin_client.post(_url("/users"), json=user_a)
            assert create_a.status_code == 201
            id_a = create_a.json()["id"]

            create_b = await admin_client.post(_url("/users"), json=user_b)
            assert create_b.status_code == 201
            id_b = create_b.json()["id"]

            # Attempt to update user_b's email to user_a's email — should conflict
            patch_resp = await admin_client.patch(
                _url(f"/users/{id_b}"),
                json={"email": user_a["email"]},
            )
            assert patch_resp.status_code == 409
        finally:
            for uid in (id_a, id_b):
                if uid is not None:
                    cleanup = await admin_client.delete(_url(f"/users/{uid}"))
                    assert cleanup.status_code in (204, 404)

    async def test_password_reset_request_returns_202(self, client: httpx.AsyncClient) -> None:
        """POST /auth/password-reset/request always returns 202 (enumeration-safe)."""
        resp = await client.post(
            _url("/auth/password-reset/request"),
            json={"email": ADMIN_EMAIL},
        )
        assert resp.status_code == 202
        assert "message" in resp.json()

    async def test_password_reset_unknown_email_still_202(self, client: httpx.AsyncClient) -> None:
        resp = await client.post(
            _url("/auth/password-reset/request"),
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 202

    async def test_create_invite_admin_returns_201(
        self, admin_client: httpx.AsyncClient, db_session: AsyncSession
    ) -> None:
        """Admin creates invite → 201."""
        unique_email = f"smoke_invite_{uuid.uuid4().hex[:8]}@test.com"
        resp = await admin_client.post(
            _url("/users/invites"),
            json={"email": unique_email, "role": "viewer"},
        )
        body = resp.json() if resp.status_code == 201 else {}
        invite_id: str | None = body.get("id")
        try:
            assert resp.status_code == 201
            assert body["role"] == "viewer"
        finally:
            if invite_id is not None:
                await db_session.execute(delete(UserInvite).where(UserInvite.id == uuid.UUID(invite_id)))
                await db_session.commit()

    async def test_totp_login_without_code_returns_403(self, client: httpx.AsyncClient) -> None:
        """TOTP-enabled user login without totp_code → 403 mfa_required."""
        resp = await client.post(
            _url("/auth/login"),
            json={"username": TOTP_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["error_code"] == "mfa_required"

    async def test_passkey_registration_options_returns_200(self, admin_client: httpx.AsyncClient) -> None:
        """Authenticated user can get passkey registration options."""
        resp = await admin_client.post(_url("/auth/passkeys/register/options"))
        assert resp.status_code == 200
        body = resp.json()
        assert "options" in body
        assert "challenge_token" in body

    async def test_passkey_login_options_unknown_user_returns_404(self, client: httpx.AsyncClient) -> None:
        """Login options for unknown username → 404."""
        resp = await client.post(
            _url("/auth/passkeys/login/options"),
            json={"username": "nonexistent_user_xyz_e2e"},
        )
        assert resp.status_code == 404

    # ── Password Reset Confirm ──────────────────────────────────────────

    async def test_password_reset_confirm_invalid_token_returns_400(self, client: httpx.AsyncClient) -> None:
        """POST /auth/password-reset/confirm with bad token → 400."""
        resp = await client.post(
            _url("/auth/password-reset/confirm"),
            json={"token": "invalid-token-xyz", "new_password": "NewStr0ngP@ss!"},  # NOSONAR
        )
        assert resp.status_code == 400

    # ── Invite List / Cancel / Resend ────────────────────────────────────

    async def test_list_invites_admin_returns_200(self, admin_client: httpx.AsyncClient) -> None:
        """GET /users/invites (admin) → 200 with items."""
        resp = await admin_client.get(_url("/users/invites"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body

    async def test_list_invites_viewer_returns_403(self, viewer_client: httpx.AsyncClient) -> None:
        """GET /users/invites (viewer) → 403."""
        resp = await viewer_client.get(_url("/users/invites"))
        assert resp.status_code == 403

    async def test_cancel_invite_not_found_returns_404(self, admin_client: httpx.AsyncClient) -> None:
        """DELETE /users/invites/{id} with non-existent ID → 404."""
        resp = await admin_client.delete(_url(f"/users/invites/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_resend_invite_returns_200(self, admin_client: httpx.AsyncClient) -> None:
        """POST /users/invites/{id}/resend → 200 with refreshed token."""
        resp = await admin_client.post(_url(f"/users/invites/{INVITE_ID}/resend"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(INVITE_ID)

    # ── Invite Accept ────────────────────────────────────────────────────

    async def test_accept_invite_invalid_token_returns_400(self, client: httpx.AsyncClient) -> None:
        """POST /auth/invite/accept with bad token → 400."""
        resp = await client.post(
            _url("/auth/invite/accept"),
            json={"token": "bad-token-xyz", "username": "newuser", "password": "Str0ngP@ssw0rd!"},  # NOSONAR
        )
        assert resp.status_code == 400

    # ── TOTP Enroll / Confirm / Disable / Recovery Count ─────────────────

    async def test_totp_enroll_confirm_disable_lifecycle(self, admin_client: httpx.AsyncClient) -> None:
        """TOTP lifecycle: enroll → confirm (bad code) → disable, with guaranteed cleanup."""
        try:
            # Enroll
            resp = await admin_client.post(_url("/auth/totp/enroll"))
            assert resp.status_code == 200
            body = resp.json()
            assert "provisioning_uri" in body
            assert "qr_code_svg" in body

            # Confirm with bad code
            resp = await admin_client.post(
                _url("/auth/totp/confirm"),
                json={"code": "000000"},
            )
            assert resp.status_code == 400
        finally:
            # Always clean up pending TOTP enrollment
            await admin_client.delete(_url("/auth/totp"))

    async def test_totp_enroll_requires_auth(self, client: httpx.AsyncClient) -> None:
        """POST /auth/totp/enroll (unauthenticated) → 401."""
        resp = await client.post(_url("/auth/totp/enroll"))
        assert resp.status_code == 401

    async def test_totp_recovery_codes_count_returns_200(self, admin_client: httpx.AsyncClient) -> None:
        """GET /auth/totp/recovery-codes/count → 200."""
        resp = await admin_client.get(_url("/auth/totp/recovery-codes/count"))
        assert resp.status_code == 200
        body = resp.json()
        assert "remaining_codes" in body

    # ── Admin TOTP Controls ──────────────────────────────────────────────

    async def test_admin_disable_user_totp_returns_204(self, admin_client: httpx.AsyncClient) -> None:
        """DELETE /users/{id}/totp (admin) → 204."""
        resp = await admin_client.delete(_url(f"/users/{TOTP_USER_ID}/totp"))
        assert resp.status_code == 204

    async def test_admin_unlock_user_totp_returns_204(self, admin_client: httpx.AsyncClient) -> None:
        """POST /users/{id}/totp/unlock (admin) → 204."""
        resp = await admin_client.post(_url(f"/users/{TOTP_USER_ID}/totp/unlock"))
        assert resp.status_code == 204

    # ── Passkey List / Rename / Delete / Register Verify / Login Verify ──

    async def test_list_passkeys_returns_200(self, admin_client: httpx.AsyncClient) -> None:
        """GET /auth/passkeys (authenticated) → 200."""
        resp = await admin_client.get(_url("/auth/passkeys"))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_passkeys_requires_auth(self, client: httpx.AsyncClient) -> None:
        """GET /auth/passkeys (unauthenticated) → 401."""
        resp = await client.get(_url("/auth/passkeys"))
        assert resp.status_code == 401

    async def test_rename_passkey_not_found_returns_404(self, admin_client: httpx.AsyncClient) -> None:
        """PATCH /auth/passkeys/{id} with non-existent ID → 404."""
        resp = await admin_client.patch(
            _url(f"/auth/passkeys/{uuid.uuid4()}"),
            json={"name": "Renamed"},
        )
        assert resp.status_code == 404

    async def test_delete_passkey_not_found_returns_404(self, admin_client: httpx.AsyncClient) -> None:
        """DELETE /auth/passkeys/{id} with non-existent ID → 404."""
        resp = await admin_client.delete(_url(f"/auth/passkeys/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_passkey_register_verify_invalid_returns_400(self, admin_client: httpx.AsyncClient) -> None:
        """POST /auth/passkeys/register/verify with bad data → 400."""
        resp = await admin_client.post(
            _url("/auth/passkeys/register/verify"),
            json={
                "credential_response": {"id": "fake"},
                "challenge_token": "invalid-jwt",
                "name": "Test",
            },
        )
        assert resp.status_code == 400

    async def test_passkey_login_verify_invalid_returns_401(self, client: httpx.AsyncClient) -> None:
        """POST /auth/passkeys/login/verify with bad data → 401."""
        resp = await client.post(
            _url("/auth/passkeys/login/verify"),
            json={
                "username": ADMIN_USERNAME,
                "credential_response": {"id": "fake"},
                "challenge_token": "invalid-jwt",
            },
        )
        assert resp.status_code == 401


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
        # New district resolution fields are present (nullable)
        assert "boundary_id" in body
        assert "district_type" in body
        assert "district_identifier" in body
        assert "district_party" in body

    async def test_election_detail_includes_metadata_fields(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elections/{ELECTION_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        # Metadata fields should be present (null for unset)
        assert "description" in body
        assert "purpose" in body
        assert "eligibility_description" in body
        assert "registration_deadline" in body
        assert "early_voting_start" in body
        assert "early_voting_end" in body
        assert "absentee_request_deadline" in body
        assert "qualifying_start" in body
        assert "qualifying_end" in body

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
            "source": "sos_feed",
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
            # Cleanup: hard-delete from DB.
            # Runs even if assertions fail to keep the DB idempotent.
            if election_id is not None:
                await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
                await db_session.commit()

    async def test_create_election_auto_parses_district(
        self, admin_client: httpx.AsyncClient, db_session: AsyncSession
    ) -> None:
        """Creating an election with a parseable district auto-populates district fields and boundary_id."""
        payload = {
            "name": f"E2E Auto-Parse {uuid.uuid4().hex[:8]}",
            "election_date": "2025-06-15",
            "election_type": "special",
            "district": "US House of Representatives - District 99",
            "source": "sos_feed",
            "data_source_url": "https://results.enr.clarityelections.com/GA/autoparse/json",
            "refresh_interval_seconds": 120,
        }
        create_resp = await admin_client.post(_url("/elections"), json=payload)
        election_id: str | None = create_resp.json().get("id") if create_resp.status_code == 201 else None
        try:
            assert create_resp.status_code == 201
            body = create_resp.json()
            assert body["district_type"] == "congressional"
            assert body["district_identifier"] == "99"
            assert body["district_party"] is None
            # Boundary ID links to seeded congressional boundary "99"
            assert body["boundary_id"] == str(BOUNDARY_ID)
        finally:
            if election_id is not None:
                await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
                await db_session.commit()

    async def test_get_election_results_empty(self, client: httpx.AsyncClient) -> None:
        """Results endpoint returns 200 with empty data when no results ingested yet."""
        resp = await client.get(_url(f"/elections/{ELECTION_ID}/results"))
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)


# ── Candidates ────────────────────────────────────────────────────────────


class TestCandidates:
    """Candidate endpoints: list, detail, CRUD, links, RBAC."""

    async def test_list_candidates_public(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/elections/{ELECTION_ID}/candidates"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body
        assert body["pagination"]["total"] >= 1

    async def test_candidate_detail_public(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/candidates/{CANDIDATE_ID}"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["full_name"] == "E2E Test Candidate"
        assert body["party"] == "Independent"
        assert len(body["links"]) >= 1

    async def test_candidate_detail_404(self, client: httpx.AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-999999999999"
        resp = await client.get(_url(f"/candidates/{fake_id}"))
        assert resp.status_code == 404

    async def test_create_candidate_admin(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.post(
            _url(f"/elections/{ELECTION_ID}/candidates"),
            json={"full_name": "E2E Created Candidate", "filing_status": "qualified"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["full_name"] == "E2E Created Candidate"
        # Clean up
        candidate_id = body["id"]
        await admin_client.delete(_url(f"/candidates/{candidate_id}"))

    async def test_update_candidate_admin(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.patch(
            _url(f"/candidates/{CANDIDATE_ID}"),
            json={"party": "Updated Party"},
        )
        assert resp.status_code == 200
        assert resp.json()["party"] == "Updated Party"
        # Restore original
        await admin_client.patch(
            _url(f"/candidates/{CANDIDATE_ID}"),
            json={"party": "Independent"},
        )

    async def test_delete_candidate_admin(self, admin_client: httpx.AsyncClient) -> None:
        # Create a throwaway candidate to delete
        create_resp = await admin_client.post(
            _url(f"/elections/{ELECTION_ID}/candidates"),
            json={"full_name": "E2E Deletable Candidate"},
        )
        assert create_resp.status_code == 201
        cid = create_resp.json()["id"]
        resp = await admin_client.delete(_url(f"/candidates/{cid}"))
        assert resp.status_code == 204

    async def test_add_link_admin(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.post(
            _url(f"/candidates/{CANDIDATE_ID}/links"),
            json={"link_type": "website", "url": "https://e2e-website.com"},
        )
        assert resp.status_code == 201
        link_id = resp.json()["id"]
        # Clean up
        await admin_client.delete(_url(f"/candidates/{CANDIDATE_ID}/links/{link_id}"))

    async def test_delete_link_admin(self, admin_client: httpx.AsyncClient) -> None:
        # Create then delete
        create_resp = await admin_client.post(
            _url(f"/candidates/{CANDIDATE_ID}/links"),
            json={"link_type": "twitter", "url": "https://twitter.com/test"},
        )
        assert create_resp.status_code == 201
        link_id = create_resp.json()["id"]
        resp = await admin_client.delete(_url(f"/candidates/{CANDIDATE_ID}/links/{link_id}"))
        assert resp.status_code == 204

    async def test_viewer_cannot_create_candidate(self, viewer_client: httpx.AsyncClient) -> None:
        resp = await viewer_client.post(
            _url(f"/elections/{ELECTION_ID}/candidates"),
            json={"full_name": "Forbidden Candidate"},
        )
        assert resp.status_code == 403

    async def test_election_soft_delete_admin(self, admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
        """Admin soft-deletes an election; subsequent GET returns 404."""
        # Create a temporary election to delete
        payload = {
            "name": f"E2E Soft-Delete {uuid.uuid4().hex[:8]}",
            "election_date": "2025-08-01",
            "election_type": "special",
            "district": "Statewide",
            "source": "sos_feed",
            "data_source_url": "https://results.enr.clarityelections.com/GA/softdelete/json",
            "refresh_interval_seconds": 120,
        }
        create_resp = await admin_client.post(_url("/elections"), json=payload)
        assert create_resp.status_code == 201
        election_id = create_resp.json()["id"]

        try:
            # Soft-delete
            del_resp = await admin_client.delete(_url(f"/elections/{election_id}"))
            assert del_resp.status_code == 204

            # Deleted election should return 404
            get_resp = await admin_client.get(_url(f"/elections/{election_id}"))
            assert get_resp.status_code == 404
        finally:
            # Hard-delete from DB to fully clean up
            await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
            await db_session.commit()

    async def test_election_source_filter(self, client: httpx.AsyncClient) -> None:
        """GET /elections?source=sos_feed returns seeded sos_feed elections."""
        resp = await client.get(_url("/elections"), params={"source": "sos_feed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"], "Expected at least one sos_feed election in seeded E2E data"
        assert all(item["source"] == "sos_feed" for item in data["items"])

    async def test_election_create_manual(self, admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
        """Admin creates a manual election with boundary_id; response has source='manual'."""
        payload = {
            "name": f"E2E Manual Election {uuid.uuid4().hex[:8]}",
            "election_date": "2026-03-01",
            "election_type": "special",
            "district": "Commission District 5",
            "source": "manual",
            "boundary_id": str(BOUNDARY_ID),
        }
        create_resp = await admin_client.post(_url("/elections"), json=payload)
        election_id: str | None = create_resp.json().get("id") if create_resp.status_code == 201 else None
        try:
            assert create_resp.status_code == 201
            body = create_resp.json()
            assert body["source"] == "manual"
            assert body["data_source_url"] is None
            assert body["boundary_id"] == str(BOUNDARY_ID)
        finally:
            if election_id is not None:
                await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
                await db_session.commit()

    async def test_election_link_admin(self, admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
        """Admin links a manual election to a SoS feed URL; response has source='linked'."""
        create_payload = {
            "name": f"E2E Link Test {uuid.uuid4().hex[:8]}",
            "election_date": "2026-04-01",
            "election_type": "special",
            "district": "Statewide",
            "source": "manual",
            "boundary_id": str(BOUNDARY_ID),
        }
        create_resp = await admin_client.post(_url("/elections"), json=create_payload)
        election_id: str | None = create_resp.json().get("id") if create_resp.status_code == 201 else None
        try:
            assert create_resp.status_code == 201
            link_payload = {
                "data_source_url": "https://results.enr.clarityelections.com/GA/e2e-link/json",
            }
            link_resp = await admin_client.post(_url(f"/elections/{election_id}/link"), json=link_payload)
            assert link_resp.status_code == 200
            body = link_resp.json()
            assert body["source"] == "linked"
            assert body["data_source_url"] is not None
        finally:
            if election_id is not None:
                await db_session.execute(delete(Election).where(Election.id == uuid.UUID(election_id)))
                await db_session.commit()

    async def test_election_link_unauthenticated_returns_401(self, client: httpx.AsyncClient) -> None:
        """Unauthenticated POST /elections/{id}/link returns 401."""
        resp = await client.post(
            _url(f"/elections/{ELECTION_ID}/link"), json={"data_source_url": "https://example.com/feed.json"}
        )
        assert resp.status_code == 401


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
            params={"boundary_type": "congressional", "district_identifier": "099"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert any(o["full_name"] == "Jane E2E Doe" for o in body)

    async def test_create_official_requires_admin(self, viewer_client: httpx.AsyncClient) -> None:
        payload = {
            "boundary_type": "congressional",
            "district_identifier": "099",
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
        # Verify has_district_mismatch field is present in schema
        for item in body["items"]:
            assert "has_district_mismatch" in item

    async def test_search_voters_filter_by_mismatch(self, admin_client: httpx.AsyncClient) -> None:
        """Search with has_district_mismatch filter returns 200."""
        resp = await admin_client.get(_url("/voters"), params={"has_district_mismatch": "true"})
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body
        for item in body["items"]:
            assert item.get("has_district_mismatch") is True

    async def test_voter_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url(f"/voters/{uuid.uuid4()}"))
        assert resp.status_code == 404

    async def test_district_check_requires_auth(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(_url(f"/voters/{uuid.uuid4()}/district-check"))
        assert resp.status_code == 401

    async def test_district_check_voter_not_found(self, admin_client: httpx.AsyncClient) -> None:
        resp = await admin_client.get(_url(f"/voters/{uuid.uuid4()}/district-check"))
        assert resp.status_code == 404

    async def test_district_check_happy_path(self, admin_client: httpx.AsyncClient) -> None:
        """GET /voters/{id}/district-check returns 200 with expected fields for a real voter."""
        voters_resp = await admin_client.get(_url("/voters"), params={"page": 1, "page_size": 1})
        assert voters_resp.status_code == 200
        items = voters_resp.json()["items"]
        assert items, "E2E database has no voters — seed fixture may have failed"

        voter_id = items[0]["id"]
        resp = await admin_client.get(_url(f"/voters/{voter_id}/district-check"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["voter_id"] == voter_id
        assert "match_status" in body
        assert "mismatch_count" in body
        assert "checked_at" in body

    async def test_set_official_location_not_found(self, admin_client: httpx.AsyncClient) -> None:
        """PUT /voters/{id}/official-location returns 404 for unknown voter."""
        resp = await admin_client.put(
            _url(f"/voters/{uuid.uuid4()}/official-location"),
            json={"latitude": 33.749, "longitude": -84.388},
        )
        assert resp.status_code == 404

    async def test_clear_official_location_not_found(self, admin_client: httpx.AsyncClient) -> None:
        """DELETE /voters/{id}/official-location/override returns 404 for unknown voter."""
        resp = await admin_client.delete(_url(f"/voters/{uuid.uuid4()}/official-location/override"))
        assert resp.status_code == 404

    async def test_set_official_location_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        """Viewer role gets 403 on PUT /voters/{id}/official-location."""
        resp = await viewer_client.put(
            _url(f"/voters/{uuid.uuid4()}/official-location"),
            json={"latitude": 33.749, "longitude": -84.388},
        )
        assert resp.status_code == 403

    async def test_clear_official_location_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        """Viewer role gets 403 on DELETE /voters/{id}/official-location/override."""
        resp = await viewer_client.delete(_url(f"/voters/{uuid.uuid4()}/official-location/override"))
        assert resp.status_code == 403

    async def test_set_and_clear_official_location_happy_path(self, admin_client: httpx.AsyncClient) -> None:
        """PUT then DELETE official-location succeeds for a real voter."""
        voters_resp = await admin_client.get(_url("/voters"), params={"page": 1, "page_size": 1})
        assert voters_resp.status_code == 200
        items = voters_resp.json()["items"]
        assert items, "E2E database has no voters — seed fixture may have failed"

        voter_id = items[0]["id"]

        # Set an override
        set_resp = await admin_client.put(
            _url(f"/voters/{voter_id}/official-location"),
            json={"latitude": 33.749, "longitude": -84.388},
        )
        assert set_resp.status_code == 200
        set_body = set_resp.json()
        assert set_body["latitude"] == pytest.approx(33.749)
        assert set_body["longitude"] == pytest.approx(-84.388)
        assert set_body["is_override"] is True

        # Clear the override
        clear_resp = await admin_client.delete(_url(f"/voters/{voter_id}/official-location/override"))
        assert clear_resp.status_code == 200
        clear_body = clear_resp.json()
        assert clear_body["is_override"] is False

    async def test_batch_boundary_check_admin_200(self, admin_client: httpx.AsyncClient) -> None:
        """POST /voters/{id}/geocode/check-boundaries returns 200 with expected structure for admin."""
        resp = await admin_client.post(_url(f"/voters/{VOTER_ID}/geocode/check-boundaries"))
        assert resp.status_code == 200
        body = resp.json()
        assert "voter_id" in body
        assert "districts" in body
        assert "provider_summary" in body
        assert "total_locations" in body
        assert "total_districts" in body
        assert "checked_at" in body
        # Each provider entry must include the determined_identifier key (may be None)
        for district in body["districts"]:
            for provider in district["providers"]:
                assert "determined_identifier" in provider

    async def test_batch_boundary_check_viewer_403(self, viewer_client: httpx.AsyncClient) -> None:
        """POST /voters/{id}/geocode/check-boundaries returns 403 for viewer role."""
        resp = await viewer_client.post(_url(f"/voters/{VOTER_ID}/geocode/check-boundaries"))
        assert resp.status_code == 403


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

    async def test_batch_list_requires_auth(self, client: httpx.AsyncClient) -> None:
        """Batch list endpoint requires authentication."""
        resp = await client.get(_url("/geocoding/batch"))
        assert resp.status_code == 401

    async def test_batch_list_as_admin(self, admin_client: httpx.AsyncClient) -> None:
        """Admin can list batch geocoding jobs."""
        resp = await admin_client.get(_url("/geocoding/batch"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_batch_list_as_analyst(self, analyst_client: httpx.AsyncClient) -> None:
        """Analyst can list batch geocoding jobs."""
        resp = await analyst_client.get(_url("/geocoding/batch"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_batch_list_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        """Viewer cannot list batch geocoding jobs."""
        resp = await viewer_client.get(_url("/geocoding/batch"))
        assert resp.status_code == 403

    async def test_batch_list_status_filter(self, admin_client: httpx.AsyncClient) -> None:
        """status= query param is accepted and does not cause a 422."""
        resp = await admin_client.get(_url("/geocoding/batch"), params={"status": "pending"})
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_jobs_list_requires_auth(self, client: httpx.AsyncClient) -> None:
        """Jobs list endpoint requires authentication."""
        resp = await client.get(_url("/geocoding/jobs"))
        assert resp.status_code == 401

    async def test_jobs_list_as_admin(self, admin_client: httpx.AsyncClient) -> None:
        """Admin can list geocoding jobs."""
        resp = await admin_client.get(_url("/geocoding/jobs"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_jobs_list_as_analyst(self, analyst_client: httpx.AsyncClient) -> None:
        """Analyst can list geocoding jobs."""
        resp = await analyst_client.get(_url("/geocoding/jobs"))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body

    async def test_jobs_list_viewer_forbidden(self, viewer_client: httpx.AsyncClient) -> None:
        """Viewer cannot list geocoding jobs."""
        resp = await viewer_client.get(_url("/geocoding/jobs"))
        assert resp.status_code == 403

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
        """Batch endpoint accepts any supported provider value (not just 'census')."""
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

    async def test_batch_requires_admin(self, client: httpx.AsyncClient) -> None:
        """Batch endpoint requires authentication — anonymous request returns 401."""
        resp = await client.post(
            _url("/geocoding/batch"),
            json={"provider": "census"},
        )
        assert resp.status_code == 401

    async def test_status_requires_auth(self, client: httpx.AsyncClient) -> None:
        """Job status endpoint requires authentication — anonymous request returns 401."""
        resp = await client.get(_url(f"/geocoding/status/{uuid.uuid4()}"))
        assert resp.status_code == 401

    async def test_status_returns_job(self, admin_client: httpx.AsyncClient) -> None:
        """Job status endpoint returns a job record for a known job ID.

        Creates a batch job via the batch endpoint, then retrieves its status.
        """
        create_resp = await admin_client.post(
            _url("/geocoding/batch"),
            json={"provider": "census", "fallback": False},
        )
        assert create_resp.status_code == 202
        job_id = create_resp.json()["id"]

        status_resp = await admin_client.get(_url(f"/geocoding/status/{job_id}"))
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["id"] == job_id
        assert "status" in body
        assert "provider" in body

    async def test_geocode_all_requires_admin(self, client: httpx.AsyncClient) -> None:
        """Voter geocode-all endpoint requires authentication — anonymous returns 401."""
        resp = await client.post(_url(f"/geocoding/voter/{uuid.uuid4()}/geocode-all"))
        assert resp.status_code == 401

    async def test_geocode_all_unknown_voter_returns_404(self, admin_client: httpx.AsyncClient) -> None:
        """Voter geocode-all returns 404 for an unknown voter ID."""
        resp = await admin_client.post(_url(f"/geocoding/voter/{uuid.uuid4()}/geocode-all"))
        assert resp.status_code == 404

    async def test_cancel_job_requires_admin(self, viewer_client: httpx.AsyncClient) -> None:
        """Cancel job endpoint requires admin role — viewer gets 403."""
        resp = await viewer_client.patch(_url(f"/geocoding/jobs/{uuid.uuid4()}/cancel"))
        assert resp.status_code == 403

    async def test_cancel_nonexistent_job(self, admin_client: httpx.AsyncClient) -> None:
        """Cancel job returns 404 for a nonexistent job ID."""
        resp = await admin_client.patch(_url(f"/geocoding/jobs/{uuid.uuid4()}/cancel"))
        assert resp.status_code == 404

    async def test_fail_job_requires_admin(self, viewer_client: httpx.AsyncClient) -> None:
        """Fail job endpoint requires admin role — viewer gets 403."""
        resp = await viewer_client.patch(_url(f"/geocoding/jobs/{uuid.uuid4()}/fail"))
        assert resp.status_code == 403

    async def test_fail_nonexistent_job(self, admin_client: httpx.AsyncClient) -> None:
        """Fail job returns 404 for a nonexistent job ID."""
        resp = await admin_client.patch(
            _url(f"/geocoding/jobs/{uuid.uuid4()}/fail"),
            json={"reason": "test failure reason"},
        )
        assert resp.status_code == 404

    async def test_cancel_job_happy_path(self, admin_client: httpx.AsyncClient) -> None:
        """Admin can create a batch job and cancel it successfully."""
        create_resp = await admin_client.post(
            _url("/geocoding/batch"),
            json={"provider": "census", "fallback": False},
        )
        assert create_resp.status_code == 202
        job_id = create_resp.json()["id"]

        cancel_resp = await admin_client.patch(_url(f"/geocoding/jobs/{job_id}/cancel"))
        assert cancel_resp.status_code == 200
        body = cancel_resp.json()
        assert body["id"] == job_id
        assert body["status"] == "cancelled"
        assert body["completed_at"] is not None
        assert body["message"] == "Job cancelled successfully"

    async def test_fail_job_happy_path(self, admin_client: httpx.AsyncClient) -> None:
        """Admin can create a batch job and mark it as failed with a reason."""
        create_resp = await admin_client.post(
            _url("/geocoding/batch"),
            json={"provider": "census", "fallback": False},
        )
        assert create_resp.status_code == 202
        job_id = create_resp.json()["id"]

        fail_resp = await admin_client.patch(
            _url(f"/geocoding/jobs/{job_id}/fail"),
            json={"reason": "E2E test failure reason"},
        )
        assert fail_resp.status_code == 200
        body = fail_resp.json()
        assert body["id"] == job_id
        assert body["status"] == "failed"
        assert body["completed_at"] is not None
        assert body["message"] == "Job marked as failed"


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

    async def test_viewer_cannot_trigger_batch_geocoding(self, viewer_client: httpx.AsyncClient) -> None:
        """Viewer role cannot trigger batch geocoding (admin-only) — returns 403."""
        resp = await viewer_client.post(_url("/geocoding/batch"), json={"provider": "census"})
        assert resp.status_code == 403

    async def test_analyst_cannot_trigger_batch_geocoding(self, analyst_client: httpx.AsyncClient) -> None:
        """Analyst role cannot trigger batch geocoding (admin-only) — returns 403."""
        resp = await analyst_client.post(_url("/geocoding/batch"), json={"provider": "census"})
        assert resp.status_code == 403


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

    async def test_election_participation_has_district_mismatch_field(self, analyst_client: httpx.AsyncClient) -> None:
        """Participation response items include has_district_mismatch field."""
        resp = await analyst_client.get(_url(f"/elections/{ELECTION_ID}/participation"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"], "Expected at least one participation item for field validation"
        for item in body["items"]:
            assert "has_district_mismatch" in item

    async def test_election_participation_q_param(self, analyst_client: httpx.AsyncClient) -> None:
        """q parameter filters participation by name/reg number."""
        resp = await analyst_client.get(_url(f"/elections/{ELECTION_ID}/participation?q=NONEXISTENT_NAME_XYZ"))
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["total"] == 0
        assert body["items"] == []

    async def test_election_participation_stats_requires_auth(self, client: httpx.AsyncClient) -> None:
        """Stats endpoint requires analyst or admin role."""
        resp = await client.get(_url(f"/elections/{ELECTION_ID}/participation/stats"))
        assert resp.status_code == 401

    async def test_election_participation_stats(self, analyst_client: httpx.AsyncClient) -> None:
        """Analyst can access participation stats."""
        resp = await analyst_client.get(_url(f"/elections/{ELECTION_ID}/participation/stats"))
        assert resp.status_code == 200
        body = resp.json()
        assert "election_id" in body
        assert "by_precinct" in body
        assert "total_eligible_voters" in body
        assert "turnout_percentage" in body
