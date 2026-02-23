"""Authentication and user management service.

Handles user authentication, creation, token generation, and refresh.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.config import Settings
from voter_api.core.security import (
    create_access_token,
    create_passkey_challenge_token,
    create_refresh_token,
    decode_passkey_challenge_token,
    decode_token,
    hash_password,
    verify_password,
)
from voter_api.lib.mailer import MailDeliveryError, MailgunMailer
from voter_api.lib.passkey import PasskeyManager
from voter_api.lib.totp import TOTPManager
from voter_api.models.auth_tokens import PasswordResetToken, UserInvite
from voter_api.models.passkey import Passkey
from voter_api.models.totp import TOTPCredential, TOTPRecoveryCode
from voter_api.models.user import User
from voter_api.schemas.auth import (
    PasskeyLoginOptionsResponse,
    PasskeyRegistrationOptionsResponse,
    TokenResponse,
    UserCreateRequest,
)

_UPDATABLE_USER_FIELDS: frozenset[str] = frozenset({"email", "role", "is_active"})


class MFARequiredException(Exception):  # noqa: N818
    """Raised when a valid password was provided but TOTP code is required or invalid."""

    def __init__(self, error_code: str = "mfa_required", detail: str = "TOTP code required") -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class TOTPLockedException(Exception):  # noqa: N818
    """Raised when TOTP is locked due to too many failed attempts."""

    def __init__(self, locked_until: datetime, detail: str = "TOTP is locked") -> None:
        self.locked_until = locked_until
        self.detail = detail
        super().__init__(detail)


async def authenticate_user(
    session: AsyncSession,
    username: str,
    password: str,
    totp_code: str | None = None,
) -> User | None:
    """Authenticate a user by username, password, and optional TOTP code.

    Args:
        session: The database session.
        username: The username to authenticate.
        password: The plaintext password.
        totp_code: Optional 6-digit TOTP code or recovery code.

    Returns:
        The User if authentication succeeds, None otherwise.

    Raises:
        MFARequiredException: If TOTP is enabled but code is missing or invalid.
        TOTPLockedException: If TOTP is locked due to too many failures.
    """
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None

    # TOTP enforcement
    totp_result = await session.execute(select(TOTPCredential).where(TOTPCredential.user_id == user.id))
    totp_cred = totp_result.scalar_one_or_none()

    if totp_cred is not None and totp_cred.is_verified:
        if totp_code is None:
            raise MFARequiredException(error_code="mfa_required", detail="TOTP code required")

        from voter_api.core.config import get_settings

        settings = get_settings()
        if not settings.totp_secret_encryption_key:
            msg = "TOTP_SECRET_ENCRYPTION_KEY must be configured to use TOTP features"
            raise RuntimeError(msg)
        totp_manager = TOTPManager(
            encryption_key=settings.totp_secret_encryption_key,
            issuer=settings.webauthn_rp_name,
        )
        now = datetime.now(UTC)

        is_recovery = len(totp_code) > 6

        if is_recovery:
            # Recovery code path
            recovery_result = await session.execute(
                select(TOTPRecoveryCode).where(
                    TOTPRecoveryCode.user_id == user.id,
                    TOTPRecoveryCode.used_at.is_(None),
                )
            )
            unused_codes = recovery_result.scalars().all()
            stored_hashes = [rc.code_hash for rc in unused_codes]
            if not totp_manager.verify_recovery_code(totp_code, stored_hashes):
                logger.warning(
                    "security.totp.recovery_code_failed username={username}",
                    username=username,
                )
                raise MFARequiredException(error_code="mfa_invalid", detail="Invalid recovery code")

            # Mark the matching recovery code used
            for rc in unused_codes:
                if hashlib.sha256(totp_code.encode()).hexdigest() == rc.code_hash:
                    rc.used_at = now
                    break

            totp_cred.failed_attempts = 0
            totp_cred.locked_until = None
            logger.info(
                "security.totp.recovery_code_used username={username}",
                username=username,
            )
        else:
            # 6-digit TOTP code path
            if totp_cred.locked_until is not None and totp_cred.locked_until.replace(tzinfo=UTC) > now:
                logger.warning(
                    "security.totp.locked username={username} locked_until={locked_until}",
                    username=username,
                    locked_until=totp_cred.locked_until,
                )
                raise TOTPLockedException(
                    locked_until=totp_cred.locked_until,
                    detail=f"TOTP is locked until {totp_cred.locked_until.isoformat()}",
                )

            # Replay check (FR-020)
            if totp_cred.last_used_otp == totp_code and totp_cred.last_used_otp_at is not None:
                last_used = totp_cred.last_used_otp_at
                if last_used.tzinfo is None:
                    last_used = last_used.replace(tzinfo=UTC)
                if (now - last_used).total_seconds() <= 30:
                    logger.warning(
                        "security.totp.replay_detected username={username}",
                        username=username,
                    )
                    raise MFARequiredException(error_code="mfa_invalid", detail="TOTP code already used")

            if not totp_manager.verify_code(totp_cred.encrypted_secret, totp_code):
                totp_cred.failed_attempts += 1
                if totp_cred.failed_attempts >= settings.totp_max_attempts:
                    totp_cred.locked_until = now + timedelta(minutes=settings.totp_lockout_minutes)
                    totp_cred.failed_attempts = 0
                    await session.commit()
                    logger.warning(
                        "security.totp.locked_out username={username}",
                        username=username,
                    )
                    raise TOTPLockedException(
                        locked_until=totp_cred.locked_until,
                        detail=f"TOTP locked until {totp_cred.locked_until.isoformat()}",
                    )
                logger.warning(
                    "security.totp.failure username={username} attempts={attempts}",
                    username=username,
                    attempts=totp_cred.failed_attempts,
                )
                await session.commit()
                raise MFARequiredException(error_code="mfa_invalid", detail="Invalid TOTP code")

            # Successful TOTP verification
            totp_cred.last_used_otp = totp_code
            totp_cred.last_used_otp_at = now
            totp_cred.failed_attempts = 0
            totp_cred.locked_until = None
            logger.info(
                "security.totp.success username={username}",
                username=username,
            )

    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user


async def create_user(session: AsyncSession, request: UserCreateRequest) -> User:
    """Create a new user.

    Args:
        session: The database session.
        request: User creation request data.

    Returns:
        The created User.

    Raises:
        ValueError: If username or email already exists.
    """
    existing = await session.execute(
        select(User).where((User.username == request.username) | (User.email == request.email))
    )
    if existing.scalar_one_or_none() is not None:
        msg = "Username or email already exists"
        raise ValueError(msg)

    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role=request.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def list_users(session: AsyncSession, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
    """List users with pagination.

    Args:
        session: The database session.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (users list, total count).
    """
    count_result = await session.execute(select(func.count(User.id)))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(select(User).offset(offset).limit(page_size).order_by(User.created_at))
    users = list(result.scalars().all())
    return users, total


def generate_tokens(user: User, settings: Settings) -> TokenResponse:
    """Generate access and refresh tokens for a user.

    Args:
        user: The authenticated user.
        settings: Application settings.

    Returns:
        Token response with access and refresh tokens.
    """
    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh_token = create_refresh_token(
        subject=user.username,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        expires_days=settings.jwt_refresh_token_expire_days,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


async def refresh_access_token(
    session: AsyncSession,
    refresh_token_str: str,
    settings: Settings,
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    Args:
        session: The database session.
        refresh_token_str: The refresh token string.
        settings: Application settings.

    Returns:
        New token response.

    Raises:
        ValueError: If the refresh token is invalid or user not found.
    """
    try:
        payload = decode_token(refresh_token_str, settings.jwt_secret_key, settings.jwt_algorithm)
    except Exception as e:
        msg = "Invalid refresh token"
        raise ValueError(msg) from e

    if payload.get("type") != "refresh":
        msg = "Token is not a refresh token"
        raise ValueError(msg)

    username = payload.get("sub")
    if username is None:
        msg = "Invalid token payload"
        raise ValueError(msg)

    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        msg = "User not found or inactive"
        raise ValueError(msg)

    return generate_tokens(user, settings)


# ── Password Reset (US1) ────────────────────────────────────────────────────


async def request_password_reset(
    session: AsyncSession,
    mailer: MailgunMailer,
    settings: Settings,
    email: str,
) -> None:
    """Initiate a password reset for the given email address.

    Always returns without error to prevent email enumeration. Rate-limited
    to one request per RESET_RATE_LIMIT_MINUTES. On delivery failure, logs a
    warning and returns silently (enumeration-safe); prior tokens are preserved.

    Args:
        session: The database session.
        mailer: Configured MailgunMailer instance.
        settings: Application settings.
        email: The requester's email address.
    """
    # Look up the user (silently succeed if not found)
    user_result = await session.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if user is None:
        return  # enumeration-safe: no logging, no error

    now = datetime.now(UTC)
    rate_limit_cutoff = now - timedelta(minutes=settings.reset_rate_limit_minutes)

    # (A) Rate-limit check — if a recent token exists, return without doing anything
    existing = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > rate_limit_cutoff,
        )
    )
    if existing.scalar_one_or_none() is not None:
        logger.info(
            "security.password_reset.rate_limited email={email}",
            email=email,
        )
        return

    # Generate raw token + hash
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = now + timedelta(hours=24)

    # Send email first — stay enumeration-safe on delivery failure
    reset_url = f"token={raw_token}"  # clients construct full URL; we embed only the token value
    try:
        await mailer.send_template(
            to=email,
            subject="Reset your password",
            template_name="password_reset.html",
            context={
                "app_name": settings.webauthn_rp_name,
                "reset_url": reset_url,
            },
        )
    except MailDeliveryError:
        logger.warning("security.password_reset.delivery_failed")
        return  # stay enumeration-safe; do not invalidate existing tokens

    # Delete prior tokens only after successful delivery
    await session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))

    # Persist only after successful delivery
    row = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()

    logger.info(
        "security.password_reset.requested email={email}",
        email=email,
    )


async def confirm_password_reset(
    session: AsyncSession,
    token: str,
    new_password: str,
) -> None:
    """Complete a password reset using a raw token.

    Args:
        session: The database session.
        token: The raw token received by email.
        new_password: The new plaintext password.

    Raises:
        ValueError: If the token is invalid, expired, or already used.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(UTC)

    result = await session.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    row = result.scalar_one_or_none()

    if row is None or row.used_at is not None:
        msg = "Invalid or already used reset token"
        raise ValueError(msg)

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        msg = "Reset token has expired"
        raise ValueError(msg)

    # Update password
    user_result = await session.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        msg = "User not found"
        raise ValueError(msg)

    user.hashed_password = hash_password(new_password)
    row.used_at = now
    await session.commit()

    logger.info(
        "security.password_reset.completed user_id={user_id}",
        user_id=str(row.user_id),
    )


# ── User Invites (US2) ──────────────────────────────────────────────────────


async def create_invite(
    session: AsyncSession,
    mailer: MailgunMailer,
    settings: Settings,
    admin_id: uuid.UUID,
    email: str,
    role: str,
) -> UserInvite:
    """Create and send a user invite.

    Args:
        session: The database session.
        mailer: Configured MailgunMailer instance.
        settings: Application settings.
        admin_id: UUID of the admin creating the invite.
        email: Invitee's email address.
        role: Role to assign to the new user.

    Returns:
        The created UserInvite row.

    Raises:
        ValueError: If the email already exists as a registered user.
        MailDeliveryError: If email delivery fails (no row persisted).
    """
    # Check email not already registered
    existing_user = await session.execute(select(User).where(User.email == email))
    if existing_user.scalar_one_or_none() is not None:
        msg = "Email is already registered"
        raise ValueError(msg)

    now = datetime.now(UTC)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = now + timedelta(days=7)

    # Send email — fail-fast
    invite_url = f"token={raw_token}"
    await mailer.send_template(
        to=email,
        subject=f"You've been invited to {settings.webauthn_rp_name}",
        template_name="invite.html",
        context={
            "app_name": settings.webauthn_rp_name,
            "invite_url": invite_url,
            "role": role,
        },
    )

    row = UserInvite(
        email=email,
        role=role,
        invited_by_id=admin_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_invites(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[UserInvite], int]:
    """List pending (unexpired, unaccepted) invites.

    Args:
        session: The database session.
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (invite list, total count).
    """
    now = datetime.now(UTC)
    base = select(UserInvite).where(UserInvite.accepted_at.is_(None)).where(UserInvite.expires_at > now)
    count_result = await session.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(base.order_by(UserInvite.created_at.desc()).offset(offset).limit(page_size))
    return list(result.scalars().all()), total


async def cancel_invite(session: AsyncSession, invite_id: uuid.UUID) -> None:
    """Cancel (delete) a pending invite.

    Args:
        session: The database session.
        invite_id: UUID of the invite to cancel.

    Raises:
        ValueError: If the invite is not found.
    """
    result = await session.execute(select(UserInvite).where(UserInvite.id == invite_id))
    row = result.scalar_one_or_none()
    if row is None:
        msg = "Invite not found"
        raise ValueError(msg)
    await session.delete(row)
    await session.commit()


async def resend_invite(
    session: AsyncSession,
    mailer: MailgunMailer,
    settings: Settings,
    invite_id: uuid.UUID,
) -> UserInvite:
    """Invalidate an existing invite token and send a new one.

    Args:
        session: The database session.
        mailer: Configured MailgunMailer instance.
        settings: Application settings.
        invite_id: UUID of the invite to resend.

    Returns:
        The updated UserInvite row.

    Raises:
        ValueError: If the invite is not found or already accepted.
        MailDeliveryError: If email delivery fails.
    """
    result = await session.execute(select(UserInvite).where(UserInvite.id == invite_id))
    row = result.scalar_one_or_none()
    if row is None:
        msg = "Invite not found"
        raise ValueError(msg)
    if row.accepted_at is not None:
        msg = "Invite already accepted"
        raise ValueError(msg)

    now = datetime.now(UTC)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = now + timedelta(days=7)

    # Send email — fail-fast
    invite_url = f"token={raw_token}"
    await mailer.send_template(
        to=row.email,
        subject=f"You've been invited to {settings.webauthn_rp_name}",
        template_name="invite.html",
        context={
            "app_name": settings.webauthn_rp_name,
            "invite_url": invite_url,
            "role": row.role,
        },
    )

    row.token_hash = token_hash
    row.expires_at = expires_at
    await session.commit()
    await session.refresh(row)
    return row


async def accept_invite(
    session: AsyncSession,
    token: str,
    username: str,
    password: str,
) -> User:
    """Accept an invite and create a new user account.

    Args:
        session: The database session.
        token: The raw invite token.
        username: The chosen username.
        password: The chosen password.

    Returns:
        The newly created User.

    Raises:
        ValueError: If the token is invalid, expired, or accepted; or if
            the username already exists.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(UTC)

    result = await session.execute(select(UserInvite).where(UserInvite.token_hash == token_hash))
    row = result.scalar_one_or_none()

    if row is None or row.accepted_at is not None:
        msg = "Invalid or already accepted invite token"
        raise ValueError(msg)

    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        msg = "Invite token has expired"
        raise ValueError(msg)

    # Check username uniqueness
    existing = await session.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        msg = "Username already taken"
        raise ValueError(msg)

    # Check email uniqueness (invite email may have been registered after issuance)
    existing_email = await session.execute(select(User).where(User.email == row.email))
    if existing_email.scalar_one_or_none() is not None:
        msg = "Email already registered"
        raise ValueError(msg)

    user = User(
        username=username,
        email=row.email,
        hashed_password=hash_password(password),
        role=row.role,
    )
    session.add(user)
    row.accepted_at = now
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Get a user by ID.

    Args:
        session: The database session.
        user_id: The UUID of the user to retrieve.

    Returns:
        The User if found, None otherwise.
    """
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(session: AsyncSession, user: User, updates: dict) -> User:
    """Update a user's fields.

    Args:
        session: The database session.
        user: The User to update.
        updates: Dictionary of field names to new values.

    Returns:
        The updated User.

    Raises:
        ValueError: If the new email is already in use by another user.
    """
    if "email" in updates and updates["email"] != user.email:
        existing = await session.execute(select(User).where(User.email == updates["email"]))
        if existing.scalar_one_or_none() is not None:
            msg = "Email already in use"
            raise ValueError(msg)

    for field, value in updates.items():
        if field in _UPDATABLE_USER_FIELDS and value is not None:
            setattr(user, field, value)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        msg = "Email already in use"
        raise ValueError(msg) from e
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    """Delete a user account.

    Args:
        session: The database session.
        user: The User to delete.
    """
    await session.delete(user)
    await session.commit()


# ── TOTP (US3) ──────────────────────────────────────────────────────────────


async def enroll_totp(
    session: AsyncSession,
    totp_manager: TOTPManager,
    user: User,
) -> tuple[str, str]:
    """Initiate TOTP enrollment for a user.

    Creates (or replaces) a pending TOTPCredential and returns the provisioning
    URI and QR code SVG. The TOTP is not active until confirm_totp() is called
    with a valid code.

    Args:
        session: The database session.
        totp_manager: Configured TOTPManager instance.
        user: The user enrolling TOTP.

    Returns:
        Tuple of (provisioning_uri, qr_code_svg).
    """
    # Delete any existing (unverified or verified) TOTP credential
    await session.execute(delete(TOTPCredential).where(TOTPCredential.user_id == user.id))
    await session.execute(delete(TOTPRecoveryCode).where(TOTPRecoveryCode.user_id == user.id))

    encrypted_secret = totp_manager.generate_secret()
    provisioning_uri = totp_manager.get_provisioning_uri(encrypted_secret, user.username)
    qr_svg = totp_manager.get_qr_svg(provisioning_uri)

    cred = TOTPCredential(
        user_id=user.id,
        encrypted_secret=encrypted_secret,
        is_verified=False,
    )
    session.add(cred)
    await session.commit()

    logger.info(
        "security.totp.enrollment_initiated user_id={user_id}",
        user_id=str(user.id),
    )
    return provisioning_uri, qr_svg


async def confirm_totp(
    session: AsyncSession,
    totp_manager: TOTPManager,
    user: User,
    code: str,
) -> list[str]:
    """Confirm TOTP enrollment with a valid code, activate TOTP, and issue recovery codes.

    Args:
        session: The database session.
        totp_manager: Configured TOTPManager instance.
        user: The user confirming enrollment.
        code: The 6-digit TOTP code from the authenticator app.

    Returns:
        List of 10 raw recovery codes (shown once; only hashes stored).

    Raises:
        ValueError: If no pending credential exists or the code is invalid.
    """
    result = await session.execute(select(TOTPCredential).where(TOTPCredential.user_id == user.id))
    cred = result.scalar_one_or_none()
    if cred is None:
        msg = "No pending TOTP enrollment found"
        raise ValueError(msg)
    if not totp_manager.verify_code(cred.encrypted_secret, code):
        msg = "Invalid TOTP code"
        raise ValueError(msg)

    now = datetime.now(UTC)
    cred.is_verified = True
    cred.enrolled_at = now

    raw_codes, hashes = totp_manager.generate_recovery_codes(n=10)
    for code_hash in hashes:
        session.add(TOTPRecoveryCode(user_id=user.id, code_hash=code_hash))

    await session.commit()

    logger.info(
        "security.totp.activated user_id={user_id}",
        user_id=str(user.id),
    )
    return raw_codes


async def disable_totp(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Disable TOTP for a user by deleting credential and recovery codes.

    Args:
        session: The database session.
        user_id: The user's UUID.
    """
    await session.execute(delete(TOTPCredential).where(TOTPCredential.user_id == user_id))
    await session.execute(delete(TOTPRecoveryCode).where(TOTPRecoveryCode.user_id == user_id))
    await session.commit()
    logger.info("security.totp.disabled user_id={user_id}", user_id=str(user_id))


async def unlock_totp(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Clear TOTP lockout for a user (admin action).

    Args:
        session: The database session.
        user_id: The user's UUID.
    """
    result = await session.execute(select(TOTPCredential).where(TOTPCredential.user_id == user_id))
    cred = result.scalar_one_or_none()
    if cred is not None:
        cred.locked_until = None
        cred.failed_attempts = 0
        await session.commit()


async def get_recovery_code_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Count unused recovery codes for a user.

    Args:
        session: The database session.
        user_id: The user's UUID.

    Returns:
        Number of unused recovery codes.
    """
    result = await session.execute(
        select(func.count(TOTPRecoveryCode.id)).where(
            TOTPRecoveryCode.user_id == user_id,
            TOTPRecoveryCode.used_at.is_(None),
        )
    )
    return result.scalar_one()


# ── Passkeys (US4) ──────────────────────────────────────────────────────────


async def get_passkey_registration_options(
    session: AsyncSession,
    passkey_manager: PasskeyManager,
    settings: Settings,
    user: User,
) -> PasskeyRegistrationOptionsResponse:
    """Generate WebAuthn registration options for a user.

    Args:
        session: The database session.
        passkey_manager: Configured PasskeyManager instance.
        settings: Application settings.
        user: The user registering a passkey.

    Returns:
        PasskeyRegistrationOptionsResponse with options dict and challenge_token.
    """
    existing_result = await session.execute(select(Passkey).where(Passkey.user_id == user.id))
    existing = existing_result.scalars().all()
    existing_cred_ids = [p.credential_id for p in existing]

    options, challenge_bytes = passkey_manager.generate_registration_options(
        user_id=user.id.bytes,
        username=user.username,
        existing_credentials=existing_cred_ids,
    )
    challenge_token = create_passkey_challenge_token(
        username=user.username,
        challenge_bytes=challenge_bytes,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    import json

    from webauthn import options_to_json

    options_dict = json.loads(options_to_json(options))
    return PasskeyRegistrationOptionsResponse(options=options_dict, challenge_token=challenge_token)


async def verify_passkey_registration(
    session: AsyncSession,
    passkey_manager: PasskeyManager,
    settings: Settings,
    user: User,
    credential_response: dict,
    challenge_token: str,
    name: str | None,
) -> Passkey:
    """Verify a passkey registration and persist the credential.

    Args:
        session: The database session.
        passkey_manager: Configured PasskeyManager instance.
        settings: Application settings.
        user: The authenticated user.
        credential_response: JSON-decoded credential from the client.
        challenge_token: The challenge JWT from the options step.
        name: Optional display name for the passkey.

    Returns:
        The newly created Passkey row.

    Raises:
        ValueError: If the challenge token is invalid or verification fails.
    """
    import base64

    import jwt

    try:
        token_data = decode_passkey_challenge_token(challenge_token, settings.jwt_secret_key, settings.jwt_algorithm)
    except jwt.InvalidTokenError as exc:
        msg = "Invalid challenge token"
        raise ValueError(msg) from exc

    if token_data["username"] != user.username:
        msg = "Challenge token username mismatch"
        raise ValueError(msg)

    challenge_bytes = base64.b64decode(token_data["challenge_b64"])
    verified = passkey_manager.verify_registration(credential_response, challenge_bytes)

    now = datetime.now(UTC)
    display_name = name if name else now.isoformat()

    passkey = Passkey(
        user_id=user.id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        name=display_name,
        registered_at=now,
    )
    session.add(passkey)
    await session.commit()
    await session.refresh(passkey)

    logger.info(
        "security.passkey.registered user_id={user_id}",
        user_id=str(user.id),
    )
    return passkey


async def list_passkeys(session: AsyncSession, user_id: uuid.UUID) -> list[Passkey]:
    """List all passkeys registered for a user.

    Args:
        session: The database session.
        user_id: The user's UUID.

    Returns:
        List of Passkey rows.
    """
    result = await session.execute(select(Passkey).where(Passkey.user_id == user_id).order_by(Passkey.registered_at))
    return list(result.scalars().all())


async def rename_passkey(
    session: AsyncSession,
    user_id: uuid.UUID,
    passkey_id: uuid.UUID,
    name: str,
) -> Passkey:
    """Rename a passkey.

    Args:
        session: The database session.
        user_id: The owning user's UUID.
        passkey_id: The passkey UUID.
        name: New display name.

    Returns:
        Updated Passkey row.

    Raises:
        ValueError: If the passkey is not found.
    """
    result = await session.execute(select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user_id))
    passkey = result.scalar_one_or_none()
    if passkey is None:
        msg = "Passkey not found"
        raise ValueError(msg)
    passkey.name = name
    await session.commit()
    await session.refresh(passkey)
    return passkey


async def delete_passkey(
    session: AsyncSession,
    user_id: uuid.UUID,
    passkey_id: uuid.UUID,
) -> None:
    """Delete a passkey.

    Args:
        session: The database session.
        user_id: The owning user's UUID.
        passkey_id: The passkey UUID.

    Raises:
        ValueError: If the passkey is not found.
    """
    result = await session.execute(select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user_id))
    passkey = result.scalar_one_or_none()
    if passkey is None:
        msg = "Passkey not found"
        raise ValueError(msg)
    await session.delete(passkey)
    await session.commit()

    logger.info(
        "security.passkey.removed user_id={user_id} passkey_id={passkey_id}",
        user_id=str(user_id),
        passkey_id=str(passkey_id),
    )


async def get_passkey_login_options(
    session: AsyncSession,
    passkey_manager: PasskeyManager,
    settings: Settings,
    username: str,
) -> PasskeyLoginOptionsResponse:
    """Generate WebAuthn authentication options for passkey login.

    Args:
        session: The database session.
        passkey_manager: Configured PasskeyManager instance.
        settings: Application settings.
        username: The username initiating login.

    Returns:
        PasskeyLoginOptionsResponse with options dict and challenge_token.

    Raises:
        ValueError: If the user is not found or has no registered passkeys.
    """
    user_result = await session.execute(select(User).where(User.username == username))
    user = user_result.scalar_one_or_none()
    if user is None:
        msg = "User not found"
        raise ValueError(msg)

    passkeys_result = await session.execute(select(Passkey).where(Passkey.user_id == user.id))
    passkeys = passkeys_result.scalars().all()
    if not passkeys:
        msg = "No passkeys registered for user"
        raise ValueError(msg)

    cred_ids = [p.credential_id for p in passkeys]
    options, challenge_bytes = passkey_manager.generate_authentication_options(credentials=cred_ids)
    challenge_token = create_passkey_challenge_token(
        username=username,
        challenge_bytes=challenge_bytes,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    import json

    from webauthn import options_to_json

    options_dict = json.loads(options_to_json(options))
    return PasskeyLoginOptionsResponse(options=options_dict, challenge_token=challenge_token)


async def verify_passkey_login(
    session: AsyncSession,
    passkey_manager: PasskeyManager,
    settings: Settings,
    username: str,
    credential_response: dict,
    challenge_token: str,
) -> TokenResponse:
    """Verify a passkey authentication assertion and issue JWT tokens.

    Passkey login bypasses TOTP enforcement per spec (Option A).

    Args:
        session: The database session.
        passkey_manager: Configured PasskeyManager instance.
        settings: Application settings.
        username: The user's username.
        credential_response: JSON-decoded assertion from the client.
        challenge_token: The challenge JWT from the options step.

    Returns:
        TokenResponse with access and refresh tokens.

    Raises:
        ValueError: If the challenge is invalid, user not found, or assertion fails.
    """
    import base64

    import jwt

    try:
        token_data = decode_passkey_challenge_token(challenge_token, settings.jwt_secret_key, settings.jwt_algorithm)
    except jwt.InvalidTokenError as exc:
        msg = "Invalid challenge token"
        raise ValueError(msg) from exc

    if token_data["username"] != username:
        msg = "Challenge token username mismatch"
        raise ValueError(msg)

    challenge_bytes = base64.b64decode(token_data["challenge_b64"])

    user_result = await session.execute(select(User).where(User.username == username))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        msg = "User not found or inactive"
        raise ValueError(msg)

    # Look up passkey by credential_id from the assertion
    cred_id_b64 = credential_response.get("id") or credential_response.get("rawId")
    if cred_id_b64 is None:
        msg = "Missing credential id in assertion"
        raise ValueError(msg)

    # credential_id in DB is bytes; the client sends base64url-encoded id
    from webauthn.helpers import base64url_to_bytes

    credential_id_bytes = base64url_to_bytes(cred_id_b64)

    passkey_result = await session.execute(select(Passkey).where(Passkey.credential_id == credential_id_bytes))
    passkey = passkey_result.scalar_one_or_none()
    if passkey is None or passkey.user_id != user.id:
        logger.warning(
            "security.passkey.login_failed username={username}",
            username=username,
        )
        msg = "Passkey not found"
        raise ValueError(msg)

    try:
        new_sign_count = passkey_manager.verify_authentication(
            credential_response=credential_response,
            expected_challenge=challenge_bytes,
            credential_public_key=passkey.public_key,
            sign_count=passkey.sign_count,
        )
    except Exception as exc:
        logger.warning(
            "security.passkey.assertion_failed username={username}",
            username=username,
        )
        raise ValueError("Passkey assertion verification failed") from exc

    passkey.sign_count = new_sign_count
    passkey.last_used_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    await session.commit()

    logger.info(
        "security.passkey.login_success username={username}",
        username=username,
    )
    return generate_tokens(user, settings)
