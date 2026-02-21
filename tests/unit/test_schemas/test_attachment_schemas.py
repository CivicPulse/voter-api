"""Unit tests for meeting attachment schemas."""

import uuid
from datetime import UTC, datetime

from voter_api.schemas.meeting_attachment import (
    AttachmentListResponse,
    AttachmentResponse,
)


class TestAttachmentResponse:
    def test_valid_response(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "meeting_id": uuid.uuid4(),
            "agenda_item_id": None,
            "original_filename": "budget.pdf",
            "file_size": 1024000,
            "content_type": "application/pdf",
            "download_url": "/api/v1/attachments/abc/download",
            "created_at": datetime.now(UTC),
        }
        resp = AttachmentResponse(**data)
        assert resp.original_filename == "budget.pdf"
        assert resp.file_size == 1024000
        assert resp.download_url is not None

    def test_nullable_parent_fields(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "original_filename": "doc.docx",
            "file_size": 500,
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "created_at": datetime.now(UTC),
        }
        resp = AttachmentResponse(**data)
        assert resp.meeting_id is None
        assert resp.agenda_item_id is None
        assert resp.download_url is None

    def test_agenda_item_attachment(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "meeting_id": None,
            "agenda_item_id": uuid.uuid4(),
            "original_filename": "minutes.csv",
            "file_size": 256,
            "content_type": "text/csv",
            "created_at": datetime.now(UTC),
        }
        resp = AttachmentResponse(**data)
        assert resp.agenda_item_id is not None
        assert resp.meeting_id is None


class TestAttachmentListResponse:
    def test_empty_list(self) -> None:
        resp = AttachmentListResponse(items=[])
        assert len(resp.items) == 0

    def test_with_items(self) -> None:
        item = AttachmentResponse(
            id=uuid.uuid4(),
            original_filename="test.pdf",
            file_size=100,
            content_type="application/pdf",
            created_at=datetime.now(UTC),
        )
        resp = AttachmentListResponse(items=[item])
        assert len(resp.items) == 1
