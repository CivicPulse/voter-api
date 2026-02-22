"""Passkey library — WebAuthn registration and authentication.

Public API:
    PasskeyManager: generate registration/authentication options, verify responses.
"""

from voter_api.lib.passkey.manager import PasskeyManager

__all__ = ["PasskeyManager"]
