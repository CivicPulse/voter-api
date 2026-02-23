"""Integration tests for enhanced authentication API endpoints (009).

Covers: login (JSON body), password reset, user invites, TOTP enrollment/login,
and passkey registration/login. All service calls and external dependencies
(mailer, TOTP manager, passkey manager) are mocked.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.auth import router
from voter_api.core.config import Settings
from voter_api.core.dependencies import get_async_session, get_current_user, get_settings
from voter_api.models.passkey import Passkey
from voter_api.models.user import User
from voter_api.schemas.auth import (
    PasskeyLoginOptionsResponse,
    PasskeyRegistrationOptionsResponse,
    TokenResponse,
)
from voter_api.services.auth_service import MFARequiredException, TOTPLockedException

# ---------------------------------------------------------------------------
# Helpers: mock model factories
# ---------------------------------------------------------------------------


def _mock_user(role: str = "admin", username: str = "testadmin") -> MagicMock:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.username = username
    u.email = f"{username}@test.com"
    u.role = role
    u.is_active = True
    u.created_at = datetime.now(UTC)
    u.last_login_at = None
    return u


def _mock_passkey(name: str = "My Device", passkey_id: uuid.UUID | None = None) -> MagicMock:
    p = MagicMock(spec=Passkey)
    p.id = passkey_id or uuid.uuid4()
    p.name = name
    p.registered_at = datetime.now(UTC)
    p.last_used_at = None
    return p


def _mock_invite(**overrides: object) -> MagicMock:
    from voter_api.models.auth_tokens import UserInvite

    inv = MagicMock(spec=UserInvite)
    inv.id = overrides.get("id", uuid.uuid4())
    inv.email = overrides.get("email", "newuser@example.com")
    inv.role = overrides.get("role", "viewer")
    inv.invited_by_id = overrides.get("invited_by_id", uuid.uuid4())
    inv.expires_at = overrides.get("expires_at", datetime.now(UTC))
    inv.accepted_at = overrides.get("accepted_at")
    inv.created_at = overrides.get("created_at", datetime.now(UTC))
    return inv


def _test_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-for-production",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=30,
        jwt_refresh_token_expire_days=7,
        webauthn_rp_id="localhost",
        webauthn_rp_name="Voter API Test",
        webauthn_origin="http://localhost",
    )


# ---------------------------------------------------------------------------
# App fixtures (three auth levels: public, admin, viewer)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Async mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_admin_user() -> MagicMock:
    return _mock_user("admin", "testadmin")


@pytest.fixture
def mock_viewer_user() -> MagicMock:
    return _mock_user("viewer", "testviewer")


@pytest.fixture
def public_app(mock_session: AsyncMock) -> FastAPI:
    """App with no authenticated user (public endpoints only)."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_settings] = _test_settings
    return app


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """App with admin user injected."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_settings] = _test_settings
    return app


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """App with viewer user injected."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    app.dependency_overrides[get_settings] = _test_settings
    return app


@pytest.fixture
async def public_client(public_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=public_app), base_url="https://test") as client:
        yield client


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=admin_app), base_url="https://test") as client:
        yield client


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=viewer_app), base_url="https://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Login — JSON body
# ---------------------------------------------------------------------------


class TestLogin:
    """POST /api/v1/auth/login — accepts JSON body (breaking change from form-data)."""

    async def test_valid_credentials_return_tokens(self, public_client: AsyncClient) -> None:
        user = _mock_user()
        token_resp = TokenResponse(
            access_token="access.tok",
            refresh_token="refresh.tok",
            token_type="bearer",
            expires_in=1800,
        )
        with (
            patch("voter_api.api.v1.auth.auth_service.authenticate_user", new_callable=AsyncMock, return_value=user),
            patch("voter_api.api.v1.auth.auth_service.generate_tokens", return_value=token_resp),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["access_token"] == "access.tok"
        assert body["token_type"] == "bearer"

    async def test_form_data_rejected_with_422(self, public_client: AsyncClient) -> None:
        """Login no longer accepts form-data (breaking change)."""
        resp = await public_client.post(
            "/api/v1/auth/login",
            data={"username": "testadmin", "password": "testpassword123"},
        )
        assert resp.status_code == 422

    async def test_wrong_credentials_return_401(self, public_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.authenticate_user", new_callable=AsyncMock, return_value=None):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "nobody", "password": "wrongpass"},  # NOSONAR
            )
        assert resp.status_code == 401

    async def test_totp_required_returns_403(self, public_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.authenticate_user",
            new_callable=AsyncMock,
            side_effect=MFARequiredException(error_code="mfa_required", detail="TOTP code required"),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123"},
            )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "mfa_required"

    async def test_invalid_totp_returns_403(self, public_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.authenticate_user",
            new_callable=AsyncMock,
            side_effect=MFARequiredException(error_code="mfa_invalid", detail="Invalid TOTP code"),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123", "totp_code": "000000"},
            )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "mfa_invalid"

    async def test_totp_lockout_returns_429(self, public_client: AsyncClient) -> None:
        locked = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        with patch(
            "voter_api.api.v1.auth.auth_service.authenticate_user",
            new_callable=AsyncMock,
            side_effect=TOTPLockedException(locked_until=locked, detail="TOTP locked"),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123", "totp_code": "000000"},
            )
        assert resp.status_code == 429
        assert "locked_until" in resp.json()

    async def test_login_with_valid_totp_returns_200(self, public_client: AsyncClient) -> None:
        user = _mock_user()
        token_resp = TokenResponse(access_token="a", refresh_token="r", token_type="bearer", expires_in=1800)
        with (
            patch("voter_api.api.v1.auth.auth_service.authenticate_user", new_callable=AsyncMock, return_value=user),
            patch("voter_api.api.v1.auth.auth_service.generate_tokens", return_value=token_resp),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "testpassword123", "totp_code": "123456"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Password Reset — US1
# ---------------------------------------------------------------------------


class TestPasswordResetRequest:
    """POST /api/v1/auth/password-reset/request — enumeration-safe, always 202."""

    async def test_known_email_returns_202(self, public_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.request_password_reset",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "user@example.com"},
            )
        assert resp.status_code == 202
        assert "message" in resp.json()

    async def test_unknown_email_also_returns_202(self, public_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.request_password_reset",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "nobody@example.org"},
            )
        assert resp.status_code == 202

    async def test_mail_delivery_failure_still_returns_202(self, public_client: AsyncClient) -> None:
        """Delivery failures are handled inside the service; endpoint stays enumeration-safe."""
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.request_password_reset",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/password-reset/request",
                json={"email": "user@example.com"},
            )
        assert resp.status_code == 202

    async def test_invalid_email_returns_422(self, public_client: AsyncClient) -> None:
        resp = await public_client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": "not-an-email"},
        )
        assert resp.status_code == 422


class TestPasswordResetConfirm:
    """POST /api/v1/auth/password-reset/confirm."""

    async def test_valid_token_returns_200(self, public_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.confirm_password_reset",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await public_client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": "valid-raw-token", "new_password": "newpassword123"},
            )
        assert resp.status_code == 200
        assert "message" in resp.json()

    async def test_invalid_token_returns_400(self, public_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.confirm_password_reset",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid or already used reset token"),
        ):
            resp = await public_client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": "bad-token", "new_password": "newpassword123"},
            )
        assert resp.status_code == 400

    async def test_short_password_returns_422(self, public_client: AsyncClient) -> None:
        resp = await public_client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": "tok", "new_password": "short"},  # NOSONAR
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# User Invites — US2
# ---------------------------------------------------------------------------


class TestCreateInvite:
    """POST /api/v1/users/invites (admin only)."""

    async def test_admin_creates_invite_returns_201(self, admin_client: AsyncClient) -> None:
        invite = _mock_invite()
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch("voter_api.api.v1.auth.auth_service.create_invite", new_callable=AsyncMock, return_value=invite),
        ):
            resp = await admin_client.post(
                "/api/v1/users/invites",
                json={"email": "newuser@example.com", "role": "viewer"},
            )
        assert resp.status_code == 201
        assert resp.json()["email"] == "newuser@example.com"

    async def test_duplicate_email_returns_409(self, admin_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.create_invite",
                new_callable=AsyncMock,
                side_effect=ValueError("Email is already registered"),
            ),
        ):
            resp = await admin_client.post(
                "/api/v1/users/invites",
                json={"email": "existing@example.com", "role": "viewer"},
            )
        assert resp.status_code == 409

    async def test_viewer_cannot_create_invite(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            "/api/v1/users/invites",
            json={"email": "x@y.com", "role": "viewer"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_create_invite(self, public_client: AsyncClient) -> None:
        resp = await public_client.post(
            "/api/v1/users/invites",
            json={"email": "x@y.com", "role": "viewer"},
        )
        assert resp.status_code == 401


class TestListInvites:
    """GET /api/v1/users/invites (admin only)."""

    async def test_admin_lists_invites(self, admin_client: AsyncClient) -> None:
        invites = [_mock_invite(), _mock_invite(email="second@example.com")]
        with patch(
            "voter_api.api.v1.auth.auth_service.list_invites",
            new_callable=AsyncMock,
            return_value=(invites, 2),
        ):
            resp = await admin_client.get("/api/v1/users/invites")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    async def test_viewer_cannot_list_invites(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.get("/api/v1/users/invites")
        assert resp.status_code == 403


class TestAcceptInvite:
    """POST /api/v1/auth/invite/accept (public)."""

    async def test_valid_token_creates_account(self, public_client: AsyncClient) -> None:
        user = _mock_user("viewer", "newviewer")
        with patch("voter_api.api.v1.auth.auth_service.accept_invite", new_callable=AsyncMock, return_value=user):
            resp = await public_client.post(
                "/api/v1/auth/invite/accept",
                json={"token": "valid-token", "username": "newviewer", "password": "password123"},
            )
        assert resp.status_code == 201
        assert resp.json()["user"]["username"] == "newviewer"

    async def test_invalid_token_returns_400(self, public_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.accept_invite",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid or already accepted invite token"),
        ):
            resp = await public_client.post(
                "/api/v1/auth/invite/accept",
                json={"token": "bad-token", "username": "user", "password": "password123"},
            )
        assert resp.status_code == 400


class TestCancelInvite:
    """DELETE /api/v1/users/invites/{id} (admin only)."""

    async def test_admin_cancels_invite_returns_204(self, admin_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.cancel_invite", new_callable=AsyncMock, return_value=None):
            resp = await admin_client.delete(f"/api/v1/users/invites/{uuid.uuid4()}")
        assert resp.status_code == 204

    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.cancel_invite",
            new_callable=AsyncMock,
            side_effect=ValueError("Invite not found"),
        ):
            resp = await admin_client.delete(f"/api/v1/users/invites/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestResendInvite:
    """POST /api/v1/users/invites/{id}/resend (admin only)."""

    async def test_admin_resends_returns_200(self, admin_client: AsyncClient) -> None:
        invite = _mock_invite()
        with (
            patch("voter_api.api.v1.auth._get_mailer", return_value=MagicMock()),
            patch("voter_api.api.v1.auth.auth_service.resend_invite", new_callable=AsyncMock, return_value=invite),
        ):
            resp = await admin_client.post(f"/api/v1/users/invites/{invite.id}/resend")
        assert resp.status_code == 200

    async def test_viewer_cannot_resend(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(f"/api/v1/users/invites/{uuid.uuid4()}/resend")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TOTP — US3
# ---------------------------------------------------------------------------


class TestTOTPEnroll:
    """POST /api/v1/auth/totp/enroll (auth-required)."""

    async def test_returns_provisioning_uri_and_qr(self, admin_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_totp_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.enroll_totp",
                new_callable=AsyncMock,
                return_value=("otpauth://totp/App:user?secret=ABC", "<svg>qr</svg>"),
            ),
        ):
            resp = await admin_client.post("/api/v1/auth/totp/enroll")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provisioning_uri"].startswith("otpauth://")
        assert "<svg>" in body["qr_code_svg"]

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.post("/api/v1/auth/totp/enroll")
        assert resp.status_code == 401


class TestTOTPConfirm:
    """POST /api/v1/auth/totp/confirm (auth-required)."""

    async def test_valid_code_returns_10_recovery_codes(self, admin_client: AsyncClient) -> None:
        codes = [f"RCOV{i:04d}ABCDEFGHIJ" for i in range(10)]
        with (
            patch("voter_api.api.v1.auth._get_totp_manager", return_value=MagicMock()),
            patch("voter_api.api.v1.auth.auth_service.confirm_totp", new_callable=AsyncMock, return_value=codes),
        ):
            resp = await admin_client.post("/api/v1/auth/totp/confirm", json={"code": "123456"})
        assert resp.status_code == 200
        assert len(resp.json()["recovery_codes"]) == 10

    async def test_invalid_code_returns_400(self, admin_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_totp_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.confirm_totp",
                new_callable=AsyncMock,
                side_effect=ValueError("Invalid TOTP code"),
            ),
        ):
            resp = await admin_client.post("/api/v1/auth/totp/confirm", json={"code": "000000"})
        assert resp.status_code == 400

    async def test_code_under_6_digits_returns_422(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.post("/api/v1/auth/totp/confirm", json={"code": "1234"})
        assert resp.status_code == 422

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.post("/api/v1/auth/totp/confirm", json={"code": "123456"})
        assert resp.status_code == 401


class TestTOTPDisable:
    """DELETE /api/v1/auth/totp (auth-required)."""

    async def test_disable_returns_204(self, admin_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.disable_totp", new_callable=AsyncMock, return_value=None):
            resp = await admin_client.delete("/api/v1/auth/totp")
        assert resp.status_code == 204

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.delete("/api/v1/auth/totp")
        assert resp.status_code == 401


class TestTOTPRecoveryCount:
    """GET /api/v1/auth/totp/recovery-codes/count (auth-required)."""

    async def test_returns_count(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.get_recovery_code_count",
            new_callable=AsyncMock,
            return_value=7,
        ):
            resp = await admin_client.get("/api/v1/auth/totp/recovery-codes/count")
        assert resp.status_code == 200
        assert resp.json()["remaining_codes"] == 7

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.get("/api/v1/auth/totp/recovery-codes/count")
        assert resp.status_code == 401


class TestAdminTOTPControls:
    """DELETE /users/{id}/totp and POST /users/{id}/totp/unlock (admin-only)."""

    async def test_admin_disables_user_totp(self, admin_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.disable_totp", new_callable=AsyncMock, return_value=None):
            resp = await admin_client.delete(f"/api/v1/users/{uuid.uuid4()}/totp")
        assert resp.status_code == 204

    async def test_viewer_cannot_disable_user_totp(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.delete(f"/api/v1/users/{uuid.uuid4()}/totp")
        assert resp.status_code == 403

    async def test_admin_unlocks_totp(self, admin_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.unlock_totp", new_callable=AsyncMock, return_value=None):
            resp = await admin_client.post(f"/api/v1/users/{uuid.uuid4()}/totp/unlock")
        assert resp.status_code == 204

    async def test_viewer_cannot_unlock_totp(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(f"/api/v1/users/{uuid.uuid4()}/totp/unlock")
        assert resp.status_code == 403


class TestTOTPLockoutFlow:
    """Progressive TOTP failures → lockout on 5th attempt, recovery code bypass."""

    async def test_five_failures_trigger_429(self, public_client: AsyncClient) -> None:
        locked = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        call_count = 0

        async def _side_effect(session: object, username: str, password: str, totp_code: str | None = None) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise MFARequiredException(error_code="mfa_invalid", detail="Invalid TOTP code")
            raise TOTPLockedException(locked_until=locked, detail="TOTP locked")

        with patch("voter_api.api.v1.auth.auth_service.authenticate_user", side_effect=_side_effect):
            for _ in range(4):
                r = await public_client.post(
                    "/api/v1/auth/login",
                    json={"username": "testadmin", "password": "password1", "totp_code": "000000"},
                )
                assert r.status_code == 403
            final = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "password1", "totp_code": "000000"},
            )
        assert final.status_code == 429
        assert "locked_until" in final.json()

    async def test_recovery_code_bypasses_lockout(self, public_client: AsyncClient) -> None:
        user = _mock_user()
        token_resp = TokenResponse(access_token="a", refresh_token="r", token_type="bearer", expires_in=1800)
        with (
            patch("voter_api.api.v1.auth.auth_service.authenticate_user", new_callable=AsyncMock, return_value=user),
            patch("voter_api.api.v1.auth.auth_service.generate_tokens", return_value=token_resp),
        ):
            resp = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "password1", "totp_code": "RCOV0001ABCDEFGHIJ"},
            )
        assert resp.status_code == 200


class TestTOTPReplayPrevention:
    """Submit the same valid TOTP code twice within 30s → second call returns mfa_invalid (FR-020)."""

    async def test_replay_same_code_returns_403(self, public_client: AsyncClient) -> None:
        user = _mock_user()
        token_resp = TokenResponse(access_token="a", refresh_token="r", token_type="bearer", expires_in=1800)
        call_count = 0

        async def _side_effect(
            session: object,
            username: str,
            password: str,
            totp_code: str | None = None,
        ) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return user  # first attempt succeeds
            raise MFARequiredException(error_code="mfa_invalid", detail="TOTP code already used")

        with (
            patch(
                "voter_api.api.v1.auth.auth_service.authenticate_user",
                side_effect=_side_effect,
            ),
            patch(
                "voter_api.api.v1.auth.auth_service.generate_tokens",
                return_value=token_resp,
            ),
        ):
            first = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "password1", "totp_code": "123456"},
            )
            assert first.status_code == 200

            second = await public_client.post(
                "/api/v1/auth/login",
                json={"username": "testadmin", "password": "password1", "totp_code": "123456"},
            )
        assert second.status_code == 403
        assert second.json()["error_code"] == "mfa_invalid"


# ---------------------------------------------------------------------------
# Passkeys — US4
# ---------------------------------------------------------------------------


class TestPasskeyRegisterOptions:
    """POST /api/v1/auth/passkeys/register/options (auth-required)."""

    async def test_returns_options_and_challenge_token(self, admin_client: AsyncClient) -> None:
        expected = PasskeyRegistrationOptionsResponse(
            options={"rp": {"id": "localhost"}},
            challenge_token="reg.jwt",
        )
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.get_passkey_registration_options",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            resp = await admin_client.post("/api/v1/auth/passkeys/register/options")
        assert resp.status_code == 200
        assert "challenge_token" in resp.json()

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.post("/api/v1/auth/passkeys/register/options")
        assert resp.status_code == 401


class TestPasskeyRegisterVerify:
    """POST /api/v1/auth/passkeys/register/verify (auth-required)."""

    async def test_valid_registration_returns_201(self, admin_client: AsyncClient) -> None:
        passkey = _mock_passkey(name="My Phone")
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.verify_passkey_registration",
                new_callable=AsyncMock,
                return_value=passkey,
            ),
        ):
            resp = await admin_client.post(
                "/api/v1/auth/passkeys/register/verify",
                json={"credential_response": {"id": "abc"}, "challenge_token": "tok", "name": "My Phone"},
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "My Phone"

    async def test_invalid_credential_returns_400(self, admin_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.verify_passkey_registration",
                new_callable=AsyncMock,
                side_effect=ValueError("Invalid challenge token"),
            ),
        ):
            resp = await admin_client.post(
                "/api/v1/auth/passkeys/register/verify",
                json={"credential_response": {}, "challenge_token": "bad", "name": None},
            )
        assert resp.status_code == 400


class TestListPasskeys:
    """GET /api/v1/auth/passkeys (auth-required)."""

    async def test_returns_passkey_list(self, admin_client: AsyncClient) -> None:
        passkeys = [_mock_passkey("Laptop"), _mock_passkey("Phone")]
        with patch("voter_api.api.v1.auth.auth_service.list_passkeys", new_callable=AsyncMock, return_value=passkeys):
            resp = await admin_client.get("/api/v1/auth/passkeys")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_requires_authentication(self, public_client: AsyncClient) -> None:
        resp = await public_client.get("/api/v1/auth/passkeys")
        assert resp.status_code == 401


class TestRenamePasskey:
    """PATCH /api/v1/auth/passkeys/{id} (auth-required)."""

    async def test_rename_returns_200(self, admin_client: AsyncClient) -> None:
        pk_id = uuid.uuid4()
        passkey = _mock_passkey(name="Renamed", passkey_id=pk_id)
        with patch("voter_api.api.v1.auth.auth_service.rename_passkey", new_callable=AsyncMock, return_value=passkey):
            resp = await admin_client.patch(f"/api/v1/auth/passkeys/{pk_id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.rename_passkey",
            new_callable=AsyncMock,
            side_effect=ValueError("Passkey not found"),
        ):
            resp = await admin_client.patch(f"/api/v1/auth/passkeys/{uuid.uuid4()}", json={"name": "X"})
        assert resp.status_code == 404


class TestDeletePasskey:
    """DELETE /api/v1/auth/passkeys/{id} (auth-required)."""

    async def test_delete_returns_204(self, admin_client: AsyncClient) -> None:
        with patch("voter_api.api.v1.auth.auth_service.delete_passkey", new_callable=AsyncMock, return_value=None):
            resp = await admin_client.delete(f"/api/v1/auth/passkeys/{uuid.uuid4()}")
        assert resp.status_code == 204

    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.auth.auth_service.delete_passkey",
            new_callable=AsyncMock,
            side_effect=ValueError("Passkey not found"),
        ):
            resp = await admin_client.delete(f"/api/v1/auth/passkeys/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestPasskeyLoginOptions:
    """POST /api/v1/auth/passkeys/login/options (public)."""

    async def test_known_user_returns_200(self, public_client: AsyncClient) -> None:
        expected = PasskeyLoginOptionsResponse(options={"allowCredentials": []}, challenge_token="login.jwt")
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.get_passkey_login_options",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            resp = await public_client.post("/api/v1/auth/passkeys/login/options", json={"username": "testadmin"})
        assert resp.status_code == 200
        assert resp.json()["challenge_token"] == "login.jwt"

    async def test_unknown_user_returns_404(self, public_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.get_passkey_login_options",
                new_callable=AsyncMock,
                side_effect=ValueError("User not found"),
            ),
        ):
            resp = await public_client.post("/api/v1/auth/passkeys/login/options", json={"username": "nobody"})
        assert resp.status_code == 404


class TestPasskeyLoginVerify:
    """POST /api/v1/auth/passkeys/login/verify (public)."""

    async def test_valid_assertion_returns_tokens(self, public_client: AsyncClient) -> None:
        token_resp = TokenResponse(
            access_token="pk.access", refresh_token="pk.refresh", token_type="bearer", expires_in=1800
        )
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.verify_passkey_login",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/passkeys/login/verify",
                json={"username": "testadmin", "credential_response": {"id": "abc"}, "challenge_token": "tok"},
            )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "pk.access"

    async def test_invalid_assertion_returns_401(self, public_client: AsyncClient) -> None:
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.verify_passkey_login",
                new_callable=AsyncMock,
                side_effect=ValueError("Passkey assertion failed"),
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/passkeys/login/verify",
                json={"username": "testadmin", "credential_response": {}, "challenge_token": "bad"},
            )
        assert resp.status_code == 401

    async def test_totp_enabled_user_passkey_login_bypasses_mfa(self, public_client: AsyncClient) -> None:
        """CRITICAL: passkey login bypasses TOTP enforcement per spec (Option A).

        Even when a user has active TOTP, authenticating via passkey returns
        tokens directly with no 403 mfa_required.
        """
        token_resp = TokenResponse(
            access_token="bypass.access", refresh_token="bypass.refresh", token_type="bearer", expires_in=1800
        )
        with (
            patch("voter_api.api.v1.auth._get_passkey_manager", return_value=MagicMock()),
            patch(
                "voter_api.api.v1.auth.auth_service.verify_passkey_login",
                new_callable=AsyncMock,
                return_value=token_resp,
            ),
        ):
            resp = await public_client.post(
                "/api/v1/auth/passkeys/login/verify",
                json={"username": "totp-user", "credential_response": {"id": "cred"}, "challenge_token": "tok"},
            )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "bypass.access"
