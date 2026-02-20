"""Unit tests for meeting Pydantic schemas."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from voter_api.schemas.meeting import (
    ApprovalStatusEnum,
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingRejectRequest,
    MeetingStatusEnum,
    MeetingSummaryResponse,
    MeetingTypeEnum,
    MeetingUpdateRequest,
)


class TestMeetingEnums:
    """Tests for meeting enum types."""

    def test_meeting_type_values(self) -> None:
        assert set(MeetingTypeEnum) == {
            MeetingTypeEnum.REGULAR,
            MeetingTypeEnum.SPECIAL,
            MeetingTypeEnum.WORK_SESSION,
            MeetingTypeEnum.EMERGENCY,
            MeetingTypeEnum.PUBLIC_HEARING,
        }

    def test_meeting_status_values(self) -> None:
        assert set(MeetingStatusEnum) == {
            MeetingStatusEnum.SCHEDULED,
            MeetingStatusEnum.COMPLETED,
            MeetingStatusEnum.CANCELLED,
            MeetingStatusEnum.POSTPONED,
        }

    def test_approval_status_values(self) -> None:
        assert set(ApprovalStatusEnum) == {
            ApprovalStatusEnum.PENDING,
            ApprovalStatusEnum.APPROVED,
            ApprovalStatusEnum.REJECTED,
        }


class TestMeetingSummaryResponse:
    """Tests for MeetingSummaryResponse schema."""

    def test_from_attributes(self) -> None:
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.governing_body_id = uuid.uuid4()
        obj.governing_body_name = "Fulton County Commission"
        obj.meeting_date = datetime.now(UTC)
        obj.location = "City Hall"
        obj.meeting_type = "regular"
        obj.status = "scheduled"
        obj.approval_status = "approved"
        obj.external_source_url = None
        obj.created_at = datetime.now(UTC)

        resp = MeetingSummaryResponse.model_validate(obj)
        assert resp.meeting_type == MeetingTypeEnum.REGULAR
        assert resp.status == MeetingStatusEnum.SCHEDULED


class TestMeetingCreateRequest:
    """Tests for MeetingCreateRequest validation."""

    def test_valid_minimal(self) -> None:
        req = MeetingCreateRequest(
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="regular",
            status="scheduled",
        )
        assert req.location is None
        assert req.external_source_url is None

    def test_valid_full(self) -> None:
        req = MeetingCreateRequest(
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            location="City Hall Room 200",
            meeting_type="special",
            status="completed",
            external_source_url="https://example.com/meeting",
        )
        assert req.location == "City Hall Room 200"

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            MeetingCreateRequest(meeting_date=datetime.now(UTC))

    def test_invalid_meeting_type(self) -> None:
        with pytest.raises(ValidationError):
            MeetingCreateRequest(
                governing_body_id=uuid.uuid4(),
                meeting_date=datetime.now(UTC),
                meeting_type="invalid_type",
                status="scheduled",
            )

    def test_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            MeetingCreateRequest(
                governing_body_id=uuid.uuid4(),
                meeting_date=datetime.now(UTC),
                meeting_type="regular",
                status="invalid_status",
            )


class TestMeetingUpdateRequest:
    """Tests for MeetingUpdateRequest validation."""

    def test_all_fields_optional(self) -> None:
        req = MeetingUpdateRequest()
        assert req.meeting_date is None
        assert req.meeting_type is None

    def test_partial_update(self) -> None:
        req = MeetingUpdateRequest(status="cancelled")
        data = req.model_dump(exclude_unset=True)
        assert "status" in data
        assert "meeting_date" not in data


class TestMeetingRejectRequest:
    """Tests for MeetingRejectRequest validation."""

    def test_valid(self) -> None:
        req = MeetingRejectRequest(reason="Duplicate meeting entry")
        assert req.reason == "Duplicate meeting entry"

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MeetingRejectRequest(reason="")

    def test_missing_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            MeetingRejectRequest()


class TestMeetingDetailResponse:
    """Tests for MeetingDetailResponse schema."""

    def test_defaults(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "governing_body_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "status": "scheduled",
            "approval_status": "approved",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        resp = MeetingDetailResponse(**data)
        assert resp.agenda_item_count == 0
        assert resp.attachment_count == 0
        assert resp.video_embed_count == 0
        assert resp.submitted_by is None
        assert resp.approved_by is None
