"""Contract tests validating Pydantic response schemas match OpenAPI spec structure.

These tests verify that all response schemas can be instantiated with
expected fields and produce valid JSON-serializable output.
"""

from datetime import UTC, datetime
from uuid import uuid4

from voter_api.schemas.analysis import (
    AnalysisComparisonResponse,
    AnalysisResultResponse,
    AnalysisRunResponse,
    ComparisonItem,
    ComparisonSummary,
    PaginatedAnalysisResultResponse,
    PaginatedAnalysisRunResponse,
)
from voter_api.schemas.auth import (
    InviteAccept,
    InviteCreate,
    InviteResponse,
    LoginRequest,
    MessageResponse,
    MFARequiredError,
    PasskeyLoginOptionsResponse,
    PasskeyLoginVerifyRequest,
    PasskeyRegistrationOptionsResponse,
    PasskeyResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    TokenResponse,
    TOTPConfirmRequest,
    TOTPConfirmResponse,
    TOTPEnrollmentResponse,
    TOTPLockedError,
    UserResponse,
)
from voter_api.schemas.boundary import (
    BoundaryDetailResponse,
    BoundarySummaryResponse,
    PaginatedBoundaryResponse,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.export import (
    ExportJobResponse,
    ExportRequest,
    PaginatedExportJobResponse,
)
from voter_api.schemas.geocoding import GeocodedLocationResponse, GeocodingJobResponse
from voter_api.schemas.imports import ImportJobResponse, PaginatedImportJobResponse
from voter_api.schemas.voter import (
    PaginatedVoterResponse,
    VoterDetailResponse,
    VoterSummaryResponse,
)


class TestAuthSchemas:
    """Verify auth response schemas match OpenAPI contract."""

    def test_token_response(self) -> None:
        resp = TokenResponse(
            access_token="abc",
            refresh_token="def",
            token_type="bearer",
            expires_in=3600,
        )
        data = resp.model_dump()
        assert "access_token" in data
        assert "token_type" in data

    def test_user_response(self) -> None:
        resp = UserResponse(
            id=uuid4(),
            username="admin",
            email="admin@test.com",
            role="admin",
            is_active=True,
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "username" in data
        assert "role" in data


class TestImportSchemas:
    """Verify import response schemas match OpenAPI contract."""

    def test_import_job_response(self) -> None:
        resp = ImportJobResponse(
            id=uuid4(),
            file_name="voters.csv",
            file_type="voter_csv",
            status="completed",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "status" in data
        assert data["status"] == "completed"

    def test_paginated_import_response(self) -> None:
        resp = PaginatedImportJobResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump()
        assert "items" in data
        assert "pagination" in data


class TestVoterSchemas:
    """Verify voter response schemas match OpenAPI contract."""

    def test_voter_summary_response(self) -> None:
        resp = VoterSummaryResponse(
            id=uuid4(),
            county="FULTON",
            voter_registration_number="12345",
            status="ACTIVE",
            last_name="SMITH",
            first_name="JOHN",
            present_in_latest_import=True,
        )
        data = resp.model_dump()
        assert "voter_registration_number" in data

    def test_voter_detail_response(self) -> None:
        resp = VoterDetailResponse(
            id=uuid4(),
            county="FULTON",
            voter_registration_number="12345",
            status="ACTIVE",
            last_name="SMITH",
            first_name="JOHN",
            present_in_latest_import=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "residence_address" in data
        assert "registered_districts" in data

    def test_paginated_voter_response(self) -> None:
        resp = PaginatedVoterResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert len(resp.items) == 0


class TestGeocodingSchemas:
    """Verify geocoding response schemas match OpenAPI contract."""

    def test_geocoded_location_response(self) -> None:
        resp = GeocodedLocationResponse(
            id=uuid4(),
            voter_id=uuid4(),
            latitude=33.749,
            longitude=-84.388,
            source_type="census",
            is_primary=True,
            geocoded_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "latitude" in data
        assert "longitude" in data

    def test_geocoding_job_response(self) -> None:
        resp = GeocodingJobResponse(
            id=uuid4(),
            provider="census",
            force_regeocode=False,
            status="completed",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "provider" in data


class TestBoundarySchemas:
    """Verify boundary response schemas match OpenAPI contract."""

    def test_boundary_summary(self) -> None:
        resp = BoundarySummaryResponse(
            id=uuid4(),
            name="District 5",
            boundary_type="congressional",
            boundary_identifier="05",
            source="state",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "boundary_type" in data

    def test_boundary_detail(self) -> None:
        resp = BoundaryDetailResponse(
            id=uuid4(),
            name="District 5",
            boundary_type="congressional",
            boundary_identifier="05",
            source="state",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "geometry" in data  # should be None by default

    def test_paginated_boundary(self) -> None:
        resp = PaginatedBoundaryResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert resp.pagination.total == 0


class TestAnalysisSchemas:
    """Verify analysis response schemas match OpenAPI contract."""

    def test_analysis_run_response(self) -> None:
        resp = AnalysisRunResponse(
            id=uuid4(),
            status="completed",
            total_voters_analyzed=1000,
            match_count=900,
            mismatch_count=80,
            unable_to_analyze_count=20,
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "total_voters_analyzed" in data
        assert data["match_count"] == 900

    def test_analysis_result_response(self) -> None:
        resp = AnalysisResultResponse(
            id=uuid4(),
            analysis_run_id=uuid4(),
            voter_id=uuid4(),
            determined_boundaries={"congressional": "05"},
            registered_boundaries={"congressional": "05"},
            match_status="match",
            analyzed_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "match_status" in data
        assert "determined_boundaries" in data

    def test_paginated_analysis_run(self) -> None:
        resp = PaginatedAnalysisRunResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert len(resp.items) == 0

    def test_paginated_analysis_result(self) -> None:
        resp = PaginatedAnalysisResultResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert len(resp.items) == 0

    def test_comparison_response(self) -> None:
        resp = AnalysisComparisonResponse(
            run_a=AnalysisRunResponse(id=uuid4(), status="completed", created_at=datetime.now(UTC)),
            run_b=AnalysisRunResponse(id=uuid4(), status="completed", created_at=datetime.now(UTC)),
            summary=ComparisonSummary(newly_matched=5, newly_mismatched=2, unchanged=93, total_compared=100),
            items=[
                ComparisonItem(
                    voter_id=uuid4(),
                    voter_registration_number="12345",
                    status_in_run_a="match",
                    status_in_run_b="mismatch-district",
                    changed=True,
                )
            ],
        )
        data = resp.model_dump()
        assert data["summary"]["total_compared"] == 100
        assert len(data["items"]) == 1


class TestExportSchemas:
    """Verify export response schemas match OpenAPI contract."""

    def test_export_request(self) -> None:
        req = ExportRequest(output_format="csv")
        assert req.output_format == "csv"
        assert req.filters is not None

    def test_export_job_response(self) -> None:
        resp = ExportJobResponse(
            id=uuid4(),
            output_format="csv",
            filters={},
            status="completed",
            record_count=1000,
            file_size_bytes=50000,
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            download_url="/api/v1/exports/123/download",
        )
        data = resp.model_dump()
        assert "download_url" in data
        assert data["record_count"] == 1000

    def test_paginated_export(self) -> None:
        resp = PaginatedExportJobResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert len(resp.items) == 0


class TestEnhancedAuthSchemas:
    """Verify 009-enhanced-auth schemas match OpenAPI contract structure."""

    def test_login_request_no_totp(self) -> None:
        req = LoginRequest(username="alice", password="password123")
        data = req.model_dump()
        assert "username" in data
        assert "password" in data
        assert data["totp_code"] is None

    def test_login_request_with_totp(self) -> None:
        req = LoginRequest(username="alice", password="password123", totp_code="123456")
        assert req.totp_code == "123456"

    def test_password_reset_request(self) -> None:
        req = PasswordResetRequest(email="user@example.com")
        data = req.model_dump()
        assert "email" in data

    def test_password_reset_confirm(self) -> None:
        req = PasswordResetConfirm(token="abc123", new_password="newpassword123")
        data = req.model_dump()
        assert "token" in data
        assert "new_password" in data

    def test_message_response(self) -> None:
        resp = MessageResponse(message="Success")
        assert resp.message == "Success"

    def test_invite_create(self) -> None:
        req = InviteCreate(email="invitee@example.com", role="viewer")
        assert req.model_dump()["role"] == "viewer"

    def test_invite_response(self) -> None:
        resp = InviteResponse(
            id=uuid4(),
            email="invitee@example.com",
            role="viewer",
            invited_by_id=None,
            expires_at=datetime.now(UTC),
            accepted_at=None,
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump()
        assert "email" in data
        assert "role" in data

    def test_invite_accept(self) -> None:
        req = InviteAccept(token="abc123", username="newuser", password="password123")
        data = req.model_dump()
        assert "token" in data
        assert "username" in data

    def test_totp_enrollment_response(self) -> None:
        resp = TOTPEnrollmentResponse(
            provisioning_uri="otpauth://totp/App:alice?secret=ABC&issuer=App",
            qr_code_svg="<svg>...</svg>",
        )
        data = resp.model_dump()
        assert "provisioning_uri" in data
        assert "qr_code_svg" in data

    def test_totp_confirm_request_valid(self) -> None:
        req = TOTPConfirmRequest(code="123456")
        assert req.code == "123456"

    def test_totp_confirm_response(self) -> None:
        codes = [f"RCOV{i:02d}ABCDEFGHIJ" for i in range(10)]
        resp = TOTPConfirmResponse(recovery_codes=codes)
        assert len(resp.recovery_codes) == 10

    def test_mfa_required_error(self) -> None:
        err = MFARequiredError(detail="TOTP required", error_code="mfa_required")
        assert err.model_dump()["error_code"] == "mfa_required"

    def test_totp_locked_error(self) -> None:
        err = TOTPLockedError(detail="Locked", locked_until=datetime.now(UTC))
        assert "locked_until" in err.model_dump()

    def test_passkey_response(self) -> None:
        resp = PasskeyResponse(
            id=uuid4(),
            name="My iPhone",
            registered_at=datetime.now(UTC),
            last_used_at=None,
        )
        data = resp.model_dump()
        assert "name" in data
        assert data["last_used_at"] is None

    def test_passkey_registration_options_response(self) -> None:
        resp = PasskeyRegistrationOptionsResponse(
            options={"challenge": "abc123"},
            challenge_token="eyJ...",
        )
        assert "options" in resp.model_dump()
        assert "challenge_token" in resp.model_dump()

    def test_passkey_login_options_response(self) -> None:
        resp = PasskeyLoginOptionsResponse(
            options={"allowCredentials": []},
            challenge_token="eyJ...",
        )
        assert "options" in resp.model_dump()

    def test_passkey_login_verify_request(self) -> None:
        req = PasskeyLoginVerifyRequest(
            username="alice",
            credential_response={"id": "abc"},
            challenge_token="eyJ...",
        )
        assert req.username == "alice"
