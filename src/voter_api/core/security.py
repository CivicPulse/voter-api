"""JWT token creation/validation and password hashing.

Uses PyJWT for JWT operations and bcrypt for password hashing.
"""

import base64
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt-hashed password string.
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The bcrypt hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(
    subject: str,
    role: str,
    secret_key: str,
    algorithm: str = "HS256",
    expires_minutes: int = 30,
) -> str:
    """Create a JWT access token.

    Args:
        subject: The token subject (typically username).
        role: The user's role.
        secret_key: Secret key for signing.
        algorithm: JWT signing algorithm.
        expires_minutes: Token expiration in minutes.

    Returns:
        The encoded JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def create_refresh_token(
    subject: str,
    secret_key: str,
    algorithm: str = "HS256",
    expires_days: int = 7,
) -> str:
    """Create a JWT refresh token.

    Args:
        subject: The token subject (typically username).
        secret_key: Secret key for signing.
        algorithm: JWT signing algorithm.
        expires_days: Token expiration in days.

    Returns:
        The encoded JWT string.
    """
    expire = datetime.now(UTC) + timedelta(days=expires_days)
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.
        secret_key: Secret key used for signing.
        algorithm: JWT signing algorithm.

    Returns:
        The decoded token payload.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid.
    """
    return jwt.decode(token, secret_key, algorithms=[algorithm])


def create_passkey_challenge_token(
    username: str,
    challenge_bytes: bytes,
    secret_key: str,
    algorithm: str = "HS256",
    expires_minutes: int = 5,
) -> str:
    """Create a short-lived JWT containing a WebAuthn challenge for stateless storage.

    Args:
        username: The username initiating the passkey ceremony.
        challenge_bytes: Raw challenge bytes from WebAuthn options generation.
        secret_key: Secret key for signing.
        algorithm: JWT signing algorithm.
        expires_minutes: Token expiration in minutes (default 5).

    Returns:
        Signed JWT string with type="passkey_challenge".
    """
    challenge_b64 = base64.b64encode(challenge_bytes).decode()
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": username,
        "challenge_b64": challenge_b64,
        "exp": expire,
        "type": "passkey_challenge",
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_passkey_challenge_token(
    token: str,
    secret_key: str,
    algorithm: str = "HS256",
) -> dict:
    """Decode a passkey challenge JWT and return username and challenge bytes.

    Args:
        token: The passkey challenge JWT string.
        secret_key: Secret key used for signing.
        algorithm: JWT signing algorithm.

    Returns:
        Dict with keys "username" (str) and "challenge_b64" (str).

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidTokenError: If the token is invalid or not a passkey_challenge type.
    """
    payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    if payload.get("type") != "passkey_challenge":
        msg = "Token is not a passkey challenge token"
        raise jwt.InvalidTokenError(msg)
    return {"username": payload["sub"], "challenge_b64": payload["challenge_b64"]}
