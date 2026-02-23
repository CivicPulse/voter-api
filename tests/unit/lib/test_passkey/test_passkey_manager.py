"""Unit tests for PasskeyManager."""

from unittest.mock import MagicMock, patch

import pytest

from voter_api.lib.passkey import PasskeyManager


@pytest.fixture()
def manager() -> PasskeyManager:
    return PasskeyManager(
        rp_id="localhost",
        rp_name="Test App",
        expected_origin="http://localhost:3000",
    )


class TestGenerateRegistrationOptions:
    """Tests for PasskeyManager.generate_registration_options."""

    def test_returns_options_and_challenge(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"test-challenge-bytes"
        with patch("voter_api.lib.passkey.manager.generate_registration_options", return_value=mock_options):
            options, challenge = manager.generate_registration_options(
                user_id=b"user-id-bytes",
                username="alice",
            )
        assert options is mock_options
        assert challenge == b"test-challenge-bytes"

    def test_passes_rp_id_and_rp_name(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"challenge"
        with patch(
            "voter_api.lib.passkey.manager.generate_registration_options", return_value=mock_options
        ) as mock_gen:
            manager.generate_registration_options(user_id=b"uid", username="alice")
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["rp_id"] == "localhost"
        assert call_kwargs["rp_name"] == "Test App"

    def test_excludes_existing_credentials(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"challenge"
        existing = [b"cred-id-1", b"cred-id-2"]
        with patch(
            "voter_api.lib.passkey.manager.generate_registration_options", return_value=mock_options
        ) as mock_gen:
            manager.generate_registration_options(
                user_id=b"uid",
                username="alice",
                existing_credentials=existing,
            )
        call_kwargs = mock_gen.call_args.kwargs
        assert len(call_kwargs["exclude_credentials"]) == 2


class TestVerifyRegistration:
    """Tests for PasskeyManager.verify_registration."""

    def test_calls_verify_registration_response(self, manager: PasskeyManager) -> None:
        mock_verified = MagicMock()
        mock_credential = MagicMock()

        with (
            patch("voter_api.lib.passkey.manager.verify_registration_response", return_value=mock_verified) as mock_vrr,
            patch(
                "voter_api.lib.passkey.manager.parse_registration_credential_json",
                return_value=mock_credential,
            ),
        ):
            result = manager.verify_registration(
                credential_response={"id": "test"},
                expected_challenge=b"challenge",
            )

        mock_vrr.assert_called_once()
        assert result is mock_verified

    def test_verify_registration_passes_rp_id_and_origin(self, manager: PasskeyManager) -> None:
        mock_verified = MagicMock()
        mock_credential = MagicMock()

        with (
            patch("voter_api.lib.passkey.manager.verify_registration_response", return_value=mock_verified) as mock_vrr,
            patch(
                "voter_api.lib.passkey.manager.parse_registration_credential_json",
                return_value=mock_credential,
            ),
        ):
            manager.verify_registration(
                credential_response={"id": "test"},
                expected_challenge=b"challenge",
            )

        call_kwargs = mock_vrr.call_args.kwargs
        assert call_kwargs["expected_rp_id"] == "localhost"
        assert call_kwargs["expected_origin"] == "http://localhost:3000"

    def test_propagates_exception_from_verify(self, manager: PasskeyManager) -> None:
        mock_credential = MagicMock()
        with (
            patch(
                "voter_api.lib.passkey.manager.verify_registration_response",
                side_effect=ValueError("invalid response"),
            ),
            patch(
                "voter_api.lib.passkey.manager.parse_registration_credential_json",
                return_value=mock_credential,
            ),
            pytest.raises(ValueError, match="invalid response"),
        ):
            manager.verify_registration(
                credential_response={"id": "test"},
                expected_challenge=b"challenge",
            )


class TestGenerateAuthenticationOptions:
    """Tests for PasskeyManager.generate_authentication_options."""

    def test_returns_options_and_challenge(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"auth-challenge"
        with patch("voter_api.lib.passkey.manager.generate_authentication_options", return_value=mock_options):
            options, challenge = manager.generate_authentication_options(credentials=[b"cred-1"])
        assert options is mock_options
        assert challenge == b"auth-challenge"

    def test_passes_rp_id(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"challenge"
        with patch(
            "voter_api.lib.passkey.manager.generate_authentication_options", return_value=mock_options
        ) as mock_gen:
            manager.generate_authentication_options(credentials=[b"cred-1"])
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["rp_id"] == "localhost"

    def test_allow_credentials_count_matches(self, manager: PasskeyManager) -> None:
        mock_options = MagicMock()
        mock_options.challenge = b"challenge"
        with patch(
            "voter_api.lib.passkey.manager.generate_authentication_options", return_value=mock_options
        ) as mock_gen:
            manager.generate_authentication_options(credentials=[b"cred-1", b"cred-2"])
        call_kwargs = mock_gen.call_args.kwargs
        assert len(call_kwargs["allow_credentials"]) == 2


class TestVerifyAuthentication:
    """Tests for PasskeyManager.verify_authentication."""

    def test_returns_new_sign_count(self, manager: PasskeyManager) -> None:
        mock_result = MagicMock()
        mock_result.new_sign_count = 42
        mock_credential = MagicMock()

        with (
            patch("voter_api.lib.passkey.manager.verify_authentication_response", return_value=mock_result),
            patch(
                "voter_api.lib.passkey.manager.parse_authentication_credential_json",
                return_value=mock_credential,
            ),
        ):
            new_count = manager.verify_authentication(
                credential_response={"id": "test"},
                expected_challenge=b"challenge",
                credential_public_key=b"pubkey",
                sign_count=0,
            )
        assert new_count == 42

    def test_propagates_exception_from_verify(self, manager: PasskeyManager) -> None:
        mock_credential = MagicMock()
        with (
            patch(
                "voter_api.lib.passkey.manager.verify_authentication_response",
                side_effect=ValueError("assertion failed"),
            ),
            patch(
                "voter_api.lib.passkey.manager.parse_authentication_credential_json",
                return_value=mock_credential,
            ),
            pytest.raises(ValueError, match="assertion failed"),
        ):
            manager.verify_authentication(
                credential_response={"id": "test"},
                expected_challenge=b"challenge",
                credential_public_key=b"pubkey",
                sign_count=0,
            )
