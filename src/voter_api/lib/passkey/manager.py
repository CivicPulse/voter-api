"""Passkey (WebAuthn) manager wrapping the Duo Security webauthn library."""

import json

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    parse_authentication_credential_json,
    parse_registration_credential_json,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.registration.verify_registration_response import VerifiedRegistration


class PasskeyManager:
    """WebAuthn registration and authentication helper.

    Wraps the py_webauthn (Duo Security) library to provide registration and
    authentication ceremonies for passkey support.

    Args:
        rp_id: Relying party ID (domain name, e.g. "example.com").
        rp_name: Relying party display name shown in authenticator dialogs.
        expected_origin: Expected origin for ceremony verification (e.g. "https://example.com").
    """

    def __init__(self, rp_id: str, rp_name: str, expected_origin: str) -> None:
        self._rp_id = rp_id
        self._rp_name = rp_name
        self._expected_origin = expected_origin

    def generate_registration_options(
        self,
        user_id: bytes,
        username: str,
        existing_credentials: list[bytes] | None = None,
    ) -> tuple[PublicKeyCredentialCreationOptions, bytes]:
        """Generate WebAuthn registration options.

        Args:
            user_id: User's unique identifier as bytes.
            username: User's display name shown in the authenticator.
            existing_credentials: List of already-registered credential IDs to exclude.

        Returns:
            Tuple of (options_object, challenge_bytes). options_object can be
            serialized to a dict via webauthn.helpers.cbor.encode or options_to_json().
        """
        exclude = [PublicKeyCredentialDescriptor(id=cid) for cid in (existing_credentials or [])]
        options = generate_registration_options(
            rp_id=self._rp_id,
            rp_name=self._rp_name,
            user_id=user_id,
            user_name=username,
            exclude_credentials=exclude,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )
        return options, options.challenge

    def verify_registration(
        self,
        credential_response: dict,
        expected_challenge: bytes,
    ) -> VerifiedRegistration:
        """Verify a WebAuthn registration credential response.

        Args:
            credential_response: The JSON-decoded credential from the client.
            expected_challenge: The challenge bytes originally sent to the client.

        Returns:
            Verified registration object with credential_id, credential_public_key, sign_count.

        Raises:
            webauthn.helpers.exceptions.InvalidCBORData: On malformed CBOR.
            webauthn.helpers.exceptions.InvalidRegistrationResponse: On verification failure.
        """
        credential_json = json.dumps(credential_response)
        credential = parse_registration_credential_json(credential_json)
        return verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=self._rp_id,
            expected_origin=self._expected_origin,
        )

    def generate_authentication_options(
        self,
        credentials: list[bytes],
    ) -> tuple[PublicKeyCredentialRequestOptions, bytes]:
        """Generate WebAuthn authentication options for a list of credentials.

        Args:
            credentials: List of credential IDs registered for the user.

        Returns:
            Tuple of (options_object, challenge_bytes).
        """
        allow = [PublicKeyCredentialDescriptor(id=cid) for cid in credentials]
        options = generate_authentication_options(
            rp_id=self._rp_id,
            allow_credentials=allow,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        return options, options.challenge

    def verify_authentication(
        self,
        credential_response: dict,
        expected_challenge: bytes,
        credential_public_key: bytes,
        sign_count: int,
    ) -> int:
        """Verify a WebAuthn authentication assertion.

        Args:
            credential_response: The JSON-decoded assertion from the client.
            expected_challenge: The challenge bytes originally sent to the client.
            credential_public_key: COSE-encoded public key bytes from the database.
            sign_count: Current sign count from the database.

        Returns:
            Updated sign count to persist in the database.

        Raises:
            webauthn.helpers.exceptions.InvalidAuthenticationResponse: On failure.
        """
        credential_json = json.dumps(credential_response)
        credential = parse_authentication_credential_json(credential_json)
        result = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=self._rp_id,
            expected_origin=self._expected_origin,
            credential_public_key=credential_public_key,
            credential_current_sign_count=sign_count,
        )
        return result.new_sign_count
