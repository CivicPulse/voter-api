"""Unit tests for TOTPManager."""

import hashlib

import pytest
from cryptography.fernet import Fernet

from voter_api.lib.totp import TOTPManager

_FERNET_KEY = Fernet.generate_key().decode()


@pytest.fixture()
def manager() -> TOTPManager:
    return TOTPManager(encryption_key=_FERNET_KEY, issuer="Test App")


class TestGenerateSecret:
    """Tests for TOTPManager.generate_secret."""

    def test_generates_non_empty_string(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0

    def test_encrypt_decrypt_roundtrip(self, manager: TOTPManager) -> None:
        encrypted = manager.generate_secret()
        decrypted = manager._decrypt_secret(encrypted)
        assert len(decrypted) >= 16
        assert decrypted.isalpha() or all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in decrypted)

    def test_generates_unique_secrets(self, manager: TOTPManager) -> None:
        s1 = manager.generate_secret()
        s2 = manager.generate_secret()
        assert s1 != s2


class TestProvisioningUri:
    """Tests for TOTPManager.get_provisioning_uri."""

    def test_returns_otpauth_uri(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        uri = manager.get_provisioning_uri(secret, "alice")
        assert uri.startswith("otpauth://totp/")

    def test_uri_contains_username(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        uri = manager.get_provisioning_uri(secret, "alice")
        assert "alice" in uri

    def test_uri_contains_issuer(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        uri = manager.get_provisioning_uri(secret, "alice")
        assert "Test+App" in uri or "Test%20App" in uri or "Test App" in uri


class TestGetQrSvg:
    """Tests for TOTPManager.get_qr_svg."""

    def test_returns_svg_string(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        uri = manager.get_provisioning_uri(secret, "alice")
        svg = manager.get_qr_svg(uri)
        assert "<svg" in svg

    def test_svg_does_not_include_xml_declaration(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        uri = manager.get_provisioning_uri(secret, "alice")
        svg = manager.get_qr_svg(uri)
        assert "<?xml" not in svg


class TestVerifyCode:
    """Tests for TOTPManager.verify_code."""

    def test_valid_code_returns_true(self, manager: TOTPManager) -> None:
        import pyotp

        secret = manager.generate_secret()
        raw = manager._decrypt_secret(secret)
        totp = pyotp.TOTP(raw)
        code = totp.now()
        assert manager.verify_code(secret, code) is True

    def test_invalid_code_returns_false(self, manager: TOTPManager) -> None:
        secret = manager.generate_secret()
        assert manager.verify_code(secret, "000000") is False

    def test_verify_code_is_stateless(self, manager: TOTPManager) -> None:
        """verify_code does NOT track or reject replays — that is the service layer's job."""
        import pyotp

        secret = manager.generate_secret()
        raw = manager._decrypt_secret(secret)
        totp = pyotp.TOTP(raw)
        code = totp.now()
        # Calling twice in succession should both return True (stateless)
        assert manager.verify_code(secret, code) is True
        assert manager.verify_code(secret, code) is True


class TestRecoveryCodes:
    """Tests for TOTPManager.generate_recovery_codes and verify_recovery_code."""

    def test_generates_exactly_10_codes_by_default(self, manager: TOTPManager) -> None:
        raw_codes, hashes = manager.generate_recovery_codes()
        assert len(raw_codes) == 10
        assert len(hashes) == 10

    def test_generates_n_codes(self, manager: TOTPManager) -> None:
        raw_codes, hashes = manager.generate_recovery_codes(n=5)
        assert len(raw_codes) == 5
        assert len(hashes) == 5

    def test_codes_are_at_least_16_alphanumeric_chars(self, manager: TOTPManager) -> None:
        raw_codes, _ = manager.generate_recovery_codes()
        for code in raw_codes:
            assert len(code) >= 16
            assert code.isalnum(), f"Code {code!r} contains non-alphanumeric characters"

    def test_hash_is_sha256_hex_digest(self, manager: TOTPManager) -> None:
        raw_codes, hashes = manager.generate_recovery_codes(n=1)
        expected = hashlib.sha256(raw_codes[0].encode()).hexdigest()
        assert hashes[0] == expected

    def test_verify_recovery_code_matches(self, manager: TOTPManager) -> None:
        raw_codes, hashes = manager.generate_recovery_codes(n=10)
        assert manager.verify_recovery_code(raw_codes[0], hashes) is True

    def test_verify_recovery_code_wrong_code(self, manager: TOTPManager) -> None:
        _, hashes = manager.generate_recovery_codes(n=10)
        assert manager.verify_recovery_code("WRONGCODEXXXXXXXX", hashes) is False

    def test_codes_are_unique(self, manager: TOTPManager) -> None:
        raw_codes, _ = manager.generate_recovery_codes(n=10)
        assert len(set(raw_codes)) == 10
