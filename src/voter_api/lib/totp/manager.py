"""TOTP manager using pyotp for code generation and Fernet for secret encryption."""

import hashlib
import secrets
import string

import pyotp
import segno
from cryptography.fernet import Fernet


class TOTPManager:
    """Manages TOTP secret generation, code verification, and recovery codes.

    This class is stateless — it does not track used codes or enforce rate limits.
    Replay prevention and lockout enforcement are the responsibility of the service layer.

    Args:
        encryption_key: Fernet key (bytes or base64-encoded string) used to
            encrypt/decrypt TOTP secrets at rest.
        issuer: Issuer name shown in authenticator apps (e.g. "Voter API").
    """

    def __init__(self, encryption_key: str | bytes, issuer: str = "Voter API") -> None:
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        self._fernet = Fernet(encryption_key)
        self._issuer = issuer

    def generate_secret(self) -> str:
        """Generate a new TOTP shared secret encrypted with Fernet.

        Returns:
            Fernet-encrypted base32 TOTP secret (as a UTF-8 string).
        """
        raw_secret = pyotp.random_base32()
        return self._fernet.encrypt(raw_secret.encode()).decode()

    def get_provisioning_uri(self, encrypted_secret: str, username: str) -> str:
        """Return an otpauth:// provisioning URI for authenticator apps.

        Args:
            encrypted_secret: Fernet-encrypted TOTP secret from the database.
            username: User's username (shown in authenticator app).

        Returns:
            otpauth://totp/... URI compatible with Google Authenticator, Authy, etc.
        """
        raw_secret = self._decrypt_secret(encrypted_secret)
        totp = pyotp.TOTP(raw_secret)
        return totp.provisioning_uri(name=username, issuer_name=self._issuer)

    def get_qr_svg(self, provisioning_uri: str) -> str:
        """Generate an inline SVG QR code for the given provisioning URI.

        Args:
            provisioning_uri: An otpauth:// URI as returned by get_provisioning_uri().

        Returns:
            SVG string that can be embedded directly in HTML.
        """
        import io

        qr = segno.make(provisioning_uri, error="M")
        buf = io.BytesIO()
        qr.save(buf, kind="svg", xmldecl=False, svgns=True)
        return buf.getvalue().decode("utf-8")

    def verify_code(self, encrypted_secret: str, code: str) -> bool:
        """Verify a 6-digit TOTP code.

        This method is stateless — it does not track replay prevention.
        The service layer must check last_used_otp/last_used_otp_at for replay prevention.

        Args:
            encrypted_secret: Fernet-encrypted TOTP secret from the database.
            code: 6-digit TOTP code submitted by the user.

        Returns:
            True if the code is valid within the current ±1 window (30s tolerance).
        """
        raw_secret = self._decrypt_secret(encrypted_secret)
        totp = pyotp.TOTP(raw_secret)
        return totp.verify(code, valid_window=1)

    def generate_recovery_codes(self, n: int = 10) -> tuple[list[str], list[str]]:
        """Generate one-time-use recovery codes.

        Args:
            n: Number of codes to generate (default 10).

        Returns:
            Tuple of (raw_codes, sha256_hashes) where raw_codes are shown to the user
            once and sha256_hashes are stored in the database.
        """
        alphabet = string.ascii_uppercase + string.digits
        raw_codes: list[str] = []
        hashes: list[str] = []
        for _ in range(n):
            code = "".join(secrets.choice(alphabet) for _ in range(16))
            raw_codes.append(code)
            hashes.append(hashlib.sha256(code.encode()).hexdigest())
        return raw_codes, hashes

    def verify_recovery_code(self, raw_code: str, stored_hashes: list[str]) -> bool:
        """Check whether a raw recovery code matches any stored hash.

        Args:
            raw_code: The raw recovery code submitted by the user.
            stored_hashes: List of SHA-256 hex digests stored in the database.

        Returns:
            True if the raw_code hashes to one of the stored_hashes.
        """
        submitted_hash = hashlib.sha256(raw_code.encode()).hexdigest()
        return submitted_hash in stored_hashes

    def _decrypt_secret(self, encrypted_secret: str) -> str:
        """Decrypt a Fernet-encrypted TOTP secret.

        Args:
            encrypted_secret: Fernet-encrypted secret string.

        Returns:
            Raw base32 TOTP secret.
        """
        return self._fernet.decrypt(encrypted_secret.encode()).decode()
