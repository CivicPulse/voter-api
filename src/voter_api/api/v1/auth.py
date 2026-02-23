"""Authentication API endpoints.

POST /auth/login, POST /auth/refresh, GET /auth/me,
GET /users, POST /users, GET /users/{user_id},
PATCH /users/{user_id}, DELETE /users/{user_id},
GET /health, GET /info,
password reset, user invites, TOTP, and passkey endpoints.
"""

import math
import subprocess
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api import __version__
from voter_api.core.config import Settings, get_settings
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.lib.mailer import MailDeliveryError, MailgunMailer
from voter_api.lib.passkey import PasskeyManager
from voter_api.lib.totp import TOTPManager
from voter_api.models.user import User
from voter_api.schemas.auth import (
    InviteAccept,
    InviteAcceptResponse,
    InviteCreate,
    InviteResponse,
    LoginRequest,
    MessageResponse,
    MFARequiredError,
    PasskeyLoginOptionsRequest,
    PasskeyLoginOptionsResponse,
    PasskeyLoginVerifyRequest,
    PasskeyRegistrationOptionsResponse,
    PasskeyRegistrationVerifyRequest,
    PasskeyRenameRequest,
    PasskeyResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    TokenResponse,
    TOTPConfirmRequest,
    TOTPConfirmResponse,
    TOTPEnrollmentResponse,
    TOTPLockedError,
    TOTPRecoveryCodesCountResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)
from voter_api.schemas.common import PaginationMeta, PaginationParams
from voter_api.services import auth_service
from voter_api.services.auth_service import MFARequiredException, TOTPLockedException


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

_MAIL_DELIVERY_ERROR = "Email delivery failed. Please try again."


def _get_mailer(settings: Settings) -> MailgunMailer:
    """Build a MailgunMailer from settings."""
    if not settings.mailgun_api_key or not settings.mailgun_domain or not settings.mailgun_from_email:
        msg = "MAILGUN_API_KEY, MAILGUN_DOMAIN, and MAILGUN_FROM_EMAIL must be configured"
        raise RuntimeError(msg)
    return MailgunMailer(
        api_key=settings.mailgun_api_key,
        domain=settings.mailgun_domain,
        from_email=settings.mailgun_from_email,
        from_name=settings.mailgun_from_name,
    )


def _get_totp_manager(settings: Settings) -> TOTPManager:
    """Build a TOTPManager from settings."""
    if not settings.totp_secret_encryption_key:
        msg = "TOTP_SECRET_ENCRYPTION_KEY must be configured to use TOTP features"
        raise RuntimeError(msg)
    return TOTPManager(
        encryption_key=settings.totp_secret_encryption_key,
        issuer=settings.webauthn_rp_name,
    )


def _get_passkey_manager(settings: Settings) -> PasskeyManager:
    """Build a PasskeyManager from settings."""
    return PasskeyManager(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        expected_origin=settings.webauthn_origin,
    )


# ── Health & Info ────────────────────────────────────────────────────────────


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


# ── Auth ─────────────────────────────────────────────────────────────────────


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Authenticate user and return JWT tokens.

    Accepts JSON body with username, password, and optional totp_code.
    Returns 403 if TOTP is required or invalid; 429 if TOTP is locked.
    """
    try:
        user = await auth_service.authenticate_user(session, request.username, request.password, request.totp_code)
    except MFARequiredException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=MFARequiredError(detail=exc.detail, error_code=exc.error_code).model_dump(),
        ) from exc
    except TOTPLockedException as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=TOTPLockedError(
                detail=exc.detail,
                locked_until=exc.locked_until,
            ).model_dump(mode="json"),
        ) from exc

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


# ── Users ─────────────────────────────────────────────────────────────────────


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


# ── Password Reset ────────────────────────────────────────────────────────────


@router.post("/auth/password-reset/request", response_model=MessageResponse, status_code=202)
async def password_reset_request(
    request: PasswordResetRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MessageResponse:
    """Request a password reset email (enumeration-safe; always 202)."""
    mailer = _get_mailer(settings)
    await auth_service.request_password_reset(session, mailer, settings, str(request.email))
    return MessageResponse(message="If that email is registered, a reset link has been sent.")


@router.post("/auth/password-reset/confirm", response_model=MessageResponse, status_code=200)
async def password_reset_confirm(
    request: PasswordResetConfirm,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> MessageResponse:
    """Complete password reset with the token received by email."""
    try:
        await auth_service.confirm_password_reset(session, request.token, request.new_password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return MessageResponse(message="Password reset successfully")


# ── User Invites ───────────────────────────────────────────────────────────────


@router.post("/users/invites", response_model=InviteResponse, status_code=201)
async def create_invite(
    request: InviteCreate,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InviteResponse:
    """Create and send a user invite (admin only)."""
    mailer = _get_mailer(settings)
    try:
        invite = await auth_service.create_invite(
            session, mailer, settings, current_user.id, str(request.email), request.role
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except MailDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_MAIL_DELIVERY_ERROR,
        ) from None
    return InviteResponse.model_validate(invite)


@router.get("/users/invites", response_model=dict)
async def list_invites(
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pagination: Annotated[PaginationParams, Depends()],
) -> dict:
    """List pending invites (admin only)."""
    invites, total = await auth_service.list_invites(session, pagination.page, pagination.page_size)
    return {
        "items": [InviteResponse.model_validate(i) for i in invites],
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
    }


@router.delete("/users/invites/{invite_id}", status_code=204)
async def cancel_invite(
    invite_id: uuid.UUID,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Cancel a pending invite (admin only)."""
    try:
        await auth_service.cancel_invite(session, invite_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(status_code=204)


@router.post("/users/invites/{invite_id}/resend", response_model=InviteResponse, status_code=200)
async def resend_invite(
    invite_id: uuid.UUID,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InviteResponse:
    """Resend an invite with a fresh token (admin only)."""
    mailer = _get_mailer(settings)
    try:
        invite = await auth_service.resend_invite(session, mailer, settings, invite_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except MailDeliveryError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_MAIL_DELIVERY_ERROR,
        ) from None
    return InviteResponse.model_validate(invite)


@router.post("/auth/invite/accept", response_model=InviteAcceptResponse, status_code=201)
async def accept_invite(
    request: InviteAccept,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> InviteAcceptResponse:
    """Accept an invite and create a new user account (public)."""
    try:
        user = await auth_service.accept_invite(session, request.token, request.username, request.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return InviteAcceptResponse(message="Account created successfully", user=UserResponse.model_validate(user))


# ── User CRUD ─────────────────────────────────────────────────────────────────
# NOTE: /users/{user_id} routes MUST come after /users/invites routes to avoid
# FastAPI matching "invites" as a UUID path parameter.


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: uuid.UUID,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Get a user by ID (admin only).

    Args:
        user_id: The UUID of the user to retrieve.
        _current_user: The authenticated admin user (enforces role; unused directly).
        session: The async database session.

    Returns:
        The requested User record.

    Raises:
        HTTPException: 404 if no user with the given ID exists.
    """
    user = await auth_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    request: UserUpdateRequest,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> User:
    """Update an existing user's details (admin only).

    All request fields are optional; only provided fields are updated. Admins
    cannot deactivate their own account or downgrade their own role.

    Args:
        user_id: The UUID of the user to update.
        request: Partial update payload (email, role, and/or is_active).
        current_user: The authenticated admin user performing the update.
        session: The async database session.

    Returns:
        The updated User record.

    Raises:
        HTTPException: 404 if the user is not found, 400 if the admin attempts
            to deactivate their own account or downgrade their own role,
            409 if the requested email is already in use.
    """
    user = await auth_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updates = request.model_dump(exclude_unset=True, exclude_none=True)

    if current_user.id == user_id:
        if updates.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate your own account",
            )
        if "role" in updates and updates["role"] != "admin":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot downgrade your own admin role",
            )

    try:
        updated = await auth_service.update_user(session, user, updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    logger.info(f"Admin {current_user.username} updated user {user_id}")
    return updated


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> None:
    """Delete a user account (admin only). Returns 204 No Content on success.

    Related nullable foreign keys (meetings.submitted_by, meetings.approved_by,
    elected_officials.approved_by_id) are automatically set to NULL via the
    ON DELETE SET NULL constraint added in migration 025.

    Args:
        user_id: The UUID of the user to delete.
        current_user: The authenticated admin user performing the deletion.
        session: The async database session.

    Raises:
        HTTPException: 400 if the admin attempts to delete their own account,
            404 if no user with the given ID exists.
    """
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    user = await auth_service.get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await auth_service.delete_user(session, user)
    logger.info(f"Admin {current_user.username} deleted user {user_id}")


# ── TOTP ──────────────────────────────────────────────────────────────────────


@router.post("/auth/totp/enroll", response_model=TOTPEnrollmentResponse, status_code=200)
async def totp_enroll(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TOTPEnrollmentResponse:
    """Initiate TOTP enrollment and return a QR code (authenticated)."""
    totp_manager = _get_totp_manager(settings)
    provisioning_uri, qr_svg = await auth_service.enroll_totp(session, totp_manager, current_user)
    return TOTPEnrollmentResponse(provisioning_uri=provisioning_uri, qr_code_svg=qr_svg)


@router.post("/auth/totp/confirm", response_model=TOTPConfirmResponse, status_code=200)
async def totp_confirm(
    request: TOTPConfirmRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TOTPConfirmResponse:
    """Confirm TOTP enrollment with a valid code; returns recovery codes (authenticated)."""
    totp_manager = _get_totp_manager(settings)
    try:
        recovery_codes = await auth_service.confirm_totp(session, totp_manager, current_user, request.code)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return TOTPConfirmResponse(recovery_codes=recovery_codes)


@router.delete("/auth/totp", status_code=204)
async def totp_disable(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Disable TOTP for the current user (authenticated)."""
    await auth_service.disable_totp(session, current_user.id)
    return Response(status_code=204)


@router.get("/auth/totp/recovery-codes/count", response_model=TOTPRecoveryCodesCountResponse, status_code=200)
async def totp_recovery_codes_count(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TOTPRecoveryCodesCountResponse:
    """Get count of remaining recovery codes (authenticated)."""
    count = await auth_service.get_recovery_code_count(session, current_user.id)
    return TOTPRecoveryCodesCountResponse(remaining_codes=count)


@router.delete("/users/{user_id}/totp", status_code=204)
async def admin_disable_totp(
    user_id: uuid.UUID,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Admin: disable TOTP for a specific user."""
    await auth_service.disable_totp(session, user_id)
    return Response(status_code=204)


@router.post("/users/{user_id}/totp/unlock", status_code=204)
async def admin_unlock_totp(
    user_id: uuid.UUID,
    _current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Admin: clear TOTP lockout for a specific user."""
    await auth_service.unlock_totp(session, user_id)
    return Response(status_code=204)


# ── Passkeys ─────────────────────────────────────────────────────────────────


@router.post("/auth/passkeys/register/options", response_model=PasskeyRegistrationOptionsResponse, status_code=200)
async def passkey_register_options(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PasskeyRegistrationOptionsResponse:
    """Get WebAuthn registration options (authenticated)."""
    passkey_manager = _get_passkey_manager(settings)
    return await auth_service.get_passkey_registration_options(session, passkey_manager, settings, current_user)


@router.post("/auth/passkeys/register/verify", response_model=PasskeyResponse, status_code=201)
async def passkey_register_verify(
    request: PasskeyRegistrationVerifyRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PasskeyResponse:
    """Verify a passkey registration response and save the credential (authenticated)."""
    passkey_manager = _get_passkey_manager(settings)
    try:
        passkey = await auth_service.verify_passkey_registration(
            session,
            passkey_manager,
            settings,
            current_user,
            request.credential_response,
            request.challenge_token,
            request.name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return PasskeyResponse.model_validate(passkey)


@router.get("/auth/passkeys", response_model=list[PasskeyResponse], status_code=200)
async def list_passkeys(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> list[PasskeyResponse]:
    """List all passkeys registered for the current user."""
    passkeys = await auth_service.list_passkeys(session, current_user.id)
    return [PasskeyResponse.model_validate(p) for p in passkeys]


@router.patch("/auth/passkeys/{passkey_id}", response_model=PasskeyResponse, status_code=200)
async def rename_passkey(
    passkey_id: uuid.UUID,
    request: PasskeyRenameRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> PasskeyResponse:
    """Rename a passkey (authenticated)."""
    try:
        passkey = await auth_service.rename_passkey(session, current_user.id, passkey_id, request.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return PasskeyResponse.model_validate(passkey)


@router.delete("/auth/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(
    passkey_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Remove a passkey (authenticated)."""
    try:
        await auth_service.delete_passkey(session, current_user.id, passkey_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(status_code=204)


@router.post("/auth/passkeys/login/options", response_model=PasskeyLoginOptionsResponse, status_code=200)
async def passkey_login_options(
    request: PasskeyLoginOptionsRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PasskeyLoginOptionsResponse:
    """Get WebAuthn authentication options for username-first passkey login (public)."""
    passkey_manager = _get_passkey_manager(settings)
    try:
        return await auth_service.get_passkey_login_options(session, passkey_manager, settings, request.username)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/auth/passkeys/login/verify", response_model=TokenResponse, status_code=200)
async def passkey_login_verify(
    request: PasskeyLoginVerifyRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Verify passkey authentication assertion and issue JWT tokens (public)."""
    passkey_manager = _get_passkey_manager(settings)
    try:
        return await auth_service.verify_passkey_login(
            session,
            passkey_manager,
            settings,
            request.username,
            request.credential_response,
            request.challenge_token,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
