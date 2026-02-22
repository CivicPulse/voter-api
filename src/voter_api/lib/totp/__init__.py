"""TOTP library — time-based one-time password management.

Public API:
    TOTPManager: generate secrets, provisioning URIs, QR SVGs, verify codes, manage recovery codes.
"""

from voter_api.lib.totp.manager import TOTPManager

__all__ = ["TOTPManager"]
