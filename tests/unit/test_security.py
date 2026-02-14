"""Security and reliability tests.

Covers JWT edge cases, input validation, middleware behavior,
and common attack vector prevention.
"""

import jwt as pyjwt
import pytest
from pydantic import ValidationError

from voter_api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from voter_api.schemas.auth import LoginRequest, UserCreateRequest


class TestJWTEdgeCases:
    """Extended JWT token validation edge cases."""

    SECRET = "test-secret-key-for-testing-32chars"

    def test_expired_token_rejected(self) -> None:
        token = create_access_token(
            subject="user",
            role="admin",
            secret_key=self.SECRET,
            expires_minutes=-1,
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(token, self.SECRET)

    def test_malformed_token_string(self) -> None:
        with pytest.raises(pyjwt.DecodeError):
            decode_token("not.a.valid.token.at.all", self.SECRET)

    def test_truncated_token_missing_signature(self) -> None:
        token = create_access_token("user", "admin", self.SECRET)
        truncated = ".".join(token.split(".")[:2])
        with pytest.raises(pyjwt.DecodeError):
            decode_token(truncated, self.SECRET)

    def test_wrong_secret_key_rejected(self) -> None:
        token = create_access_token("user", "admin", self.SECRET)
        with pytest.raises(pyjwt.InvalidSignatureError):
            decode_token(token, "completely-wrong-secret")

    def test_empty_subject_still_decodes(self) -> None:
        token = create_access_token("", "admin", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == ""

    def test_access_token_has_correct_type(self) -> None:
        token = create_access_token("user", "admin", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload.get("type") == "access"

    def test_refresh_token_has_correct_type(self) -> None:
        token = create_refresh_token("user", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload.get("type") == "refresh"

    def test_token_contains_role(self) -> None:
        token = create_access_token("user", "viewer", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["role"] == "viewer"

    def test_token_contains_subject(self) -> None:
        token = create_access_token("myuser", "admin", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "myuser"

    def test_different_algorithm_rejected(self) -> None:
        token = create_access_token("user", "admin", self.SECRET)
        with pytest.raises(pyjwt.InvalidAlgorithmError):
            pyjwt.decode(token, self.SECRET, algorithms=["RS256"])

    def test_empty_token_string(self) -> None:
        with pytest.raises(pyjwt.DecodeError):
            decode_token("", self.SECRET)

    def test_token_with_special_characters_in_subject(self) -> None:
        token = create_access_token("user@domain.com", "admin", self.SECRET)
        payload = decode_token(token, self.SECRET)
        assert payload["sub"] == "user@domain.com"


class TestPasswordSecurity:
    """Tests for password hashing and verification."""

    def test_hash_is_not_plaintext(self) -> None:
        password = "SecurePassword123!"
        hashed = hash_password(password)
        assert hashed != password

    def test_verify_correct_password(self) -> None:
        password = "TestPassword123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_passwords_produce_different_hashes(self) -> None:
        hash1 = hash_password("password1")
        hash2 = hash_password("password2")
        assert hash1 != hash2

    def test_same_password_produces_different_hashes(self) -> None:
        """Bcrypt uses random salt, so same password produces different hashes."""
        hash1 = hash_password("SamePassword")
        hash2 = hash_password("SamePassword")
        assert hash1 != hash2
        # But both verify correctly
        assert verify_password("SamePassword", hash1) is True
        assert verify_password("SamePassword", hash2) is True

    def test_empty_password_can_be_hashed(self) -> None:
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_long_password_raises_error(self) -> None:
        """Bcrypt rejects passwords over 72 bytes."""
        long_pw = "A" * 100
        with pytest.raises(ValueError, match="password cannot be longer than 72 bytes"):
            hash_password(long_pw)

    def test_72_byte_password_works(self) -> None:
        """Exactly 72-byte password is the bcrypt maximum."""
        pw = "A" * 72
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True


class TestInputValidationSecurity:
    """Tests for Pydantic schema input validation against malicious input."""

    SQL_INJECTION_PAYLOADS = [
        "'; DROP TABLE voters; --",
        "' OR '1'='1",
        "' UNION SELECT username, password FROM users --",
        "1; SELECT * FROM information_schema.tables",
    ]

    XSS_PAYLOADS = [
        '<script>alert("xss")</script>',
        '"><img src=x onerror=alert(1)>',
        "javascript:alert(document.cookie)",
    ]

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_login_username_accepts_sql_injection_as_literal(self, payload: str) -> None:
        """SQL injection in username is treated as literal string by Pydantic."""
        # LoginRequest accepts the string as-is (Pydantic doesn't sanitize)
        # The protection comes from SQLAlchemy's parameterized queries
        if len(payload) >= 3:
            request = LoginRequest(username=payload, password="password123")
            assert request.username == payload

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_login_username_xss_treated_as_literal(self, payload: str) -> None:
        """XSS payloads in username are accepted as literal strings."""
        if len(payload) >= 3:
            request = LoginRequest(username=payload, password="password123")
            assert request.username == payload

    def test_login_username_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username="ab", password="password123")

    def test_login_username_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username="a" * 101, password="password123")

    def test_login_password_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username="validuser", password="short")

    def test_user_create_invalid_role_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="newuser",
                email="user@test.com",
                password="password123",
                role="superadmin",  # not in allowed roles
            )

    def test_user_create_valid_roles_accepted(self) -> None:
        for role in ("admin", "analyst", "viewer"):
            request = UserCreateRequest(
                username="newuser",
                email="user@test.com",
                password="password123",
                role=role,
            )
            assert request.role == role

    def test_user_create_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UserCreateRequest(
                username="newuser",
                email="not-an-email",
                password="password123",
                role="viewer",
            )


class TestExportSchemaValidation:
    """Tests for export schema input validation."""

    def test_valid_output_formats(self) -> None:
        from voter_api.schemas.export import ExportRequest

        for fmt in ("csv", "json", "geojson"):
            req = ExportRequest(output_format=fmt)
            assert req.output_format == fmt

    def test_invalid_output_format_rejected(self) -> None:
        from voter_api.schemas.export import ExportRequest

        with pytest.raises(ValidationError):
            ExportRequest(output_format="xml")

    def test_sql_injection_in_format_rejected(self) -> None:
        from voter_api.schemas.export import ExportRequest

        with pytest.raises(ValidationError):
            ExportRequest(output_format="csv; DROP TABLE voters")


class TestAnalysisSchemaValidation:
    """Tests for analysis schema validation."""

    def test_trigger_request_optional_fields(self) -> None:
        from voter_api.schemas.analysis import TriggerAnalysisRequest

        req = TriggerAnalysisRequest()
        assert req.county is None
        assert req.notes is None

    def test_trigger_request_with_values(self) -> None:
        from voter_api.schemas.analysis import TriggerAnalysisRequest

        req = TriggerAnalysisRequest(county="FULTON", notes="Test analysis")
        assert req.county == "FULTON"
        assert req.notes == "Test analysis"


class TestGeocodingResultValidation:
    """Tests for GeocodingResult dataclass validation."""

    def test_valid_coordinates(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        result = GeocodingResult(latitude=33.749, longitude=-84.388)
        assert result.latitude == 33.749
        assert result.longitude == -84.388

    def test_latitude_out_of_range(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        with pytest.raises(ValueError, match="latitude must be between"):
            GeocodingResult(latitude=91.0, longitude=0.0)

    def test_latitude_negative_out_of_range(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        with pytest.raises(ValueError, match="latitude must be between"):
            GeocodingResult(latitude=-91.0, longitude=0.0)

    def test_longitude_out_of_range(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        with pytest.raises(ValueError, match="longitude must be between"):
            GeocodingResult(latitude=0.0, longitude=181.0)

    def test_confidence_score_out_of_range(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        with pytest.raises(ValueError, match="confidence_score must be between"):
            GeocodingResult(latitude=0.0, longitude=0.0, confidence_score=1.5)

    def test_confidence_score_negative(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        with pytest.raises(ValueError, match="confidence_score must be between"):
            GeocodingResult(latitude=0.0, longitude=0.0, confidence_score=-0.1)

    def test_boundary_latitude_values(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingResult

        # Boundary values should be accepted
        GeocodingResult(latitude=90.0, longitude=0.0)
        GeocodingResult(latitude=-90.0, longitude=0.0)
        GeocodingResult(latitude=0.0, longitude=180.0)
        GeocodingResult(latitude=0.0, longitude=-180.0)


class TestGeocodingProviderError:
    """Tests for GeocodingProviderError."""

    def test_error_attributes(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingProviderError

        error = GeocodingProviderError("census", "timeout", status_code=504)
        assert error.provider_name == "census"
        assert error.message == "timeout"
        assert error.status_code == 504
        assert "census: timeout" in str(error)

    def test_error_without_status_code(self) -> None:
        from voter_api.lib.geocoder.base import GeocodingProviderError

        error = GeocodingProviderError("google", "connection refused")
        assert error.status_code is None
