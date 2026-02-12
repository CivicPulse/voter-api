"""JWT token creation/validation and password hashing.

Uses PyJWT for JWT operations and passlib with bcrypt for password hashing.
"""

from datetime import UTC, datetime, timedelta

import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The plaintext password to hash.

    Returns:
        The bcrypt-hashed password string.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The bcrypt hash to verify against.

    Returns:
        True if the password matches, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


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
