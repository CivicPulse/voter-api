"""Unit tests for meeting attachment service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.meeting_attachment_service import (
    delete_attachment,
    download_attachment,
    get_attachment,
    list_attachments,
    upload_attachment,
)


def _mock_attachment(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "agenda_item_id": None,
        "original_filename": "budget.pdf",
        "stored_path": "2026/02/abc123.pdf",
        "file_size": 1024,
        "content_type": "application/pdf",
        "deleted_at": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestListAttachments:
    @pytest.mark.asyncio
    async def test_lists_by_meeting(self) -> None:
        session = AsyncMock()
        attachments = [_mock_attachment()]
        result = MagicMock()
        result.scalars.return_value.all.return_value = attachments
        session.execute = AsyncMock(return_value=result)

        items = await list_attachments(session, meeting_id=uuid.uuid4())
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_lists_by_agenda_item(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        items = await list_attachments(session, agenda_item_id=uuid.uuid4())
        assert len(items) == 0


class TestGetAttachment:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        session = AsyncMock()
        att = _mock_attachment()
        result = MagicMock()
        result.scalar_one_or_none.return_value = att
        session.execute = AsyncMock(return_value=result)

        found = await get_attachment(session, att.id)
        assert found is att

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        found = await get_attachment(session, uuid.uuid4())
        assert found is None


class TestUploadAttachment:
    @pytest.mark.asyncio
    async def test_valid_upload(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()
        storage.save = AsyncMock(return_value="2026/02/abc.pdf")

        # _require_meeting
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = uuid.uuid4()
        session.execute = AsyncMock(return_value=meeting_result)

        await upload_attachment(
            session,
            file_content=b"fake pdf content",
            filename="budget.pdf",
            content_type="application/pdf",
            meeting_id=uuid.uuid4(),
            storage=storage,
        )
        session.add.assert_called_once()
        storage.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_format_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with pytest.raises(ValueError, match="Unsupported file format"):
            await upload_attachment(
                session,
                file_content=b"binary",
                filename="malware.exe",
                content_type="application/x-msdownload",
                meeting_id=uuid.uuid4(),
                storage=storage,
            )

    @pytest.mark.asyncio
    async def test_oversized_file_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with pytest.raises(ValueError, match="exceeds maximum size"):
            await upload_attachment(
                session,
                file_content=b"x" * (51 * 1024 * 1024),
                filename="huge.pdf",
                content_type="application/pdf",
                meeting_id=uuid.uuid4(),
                storage=storage,
            )

    @pytest.mark.asyncio
    async def test_both_parents_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with pytest.raises(ValueError, match="Exactly one of meeting_id or agenda_item_id"):
            await upload_attachment(
                session,
                file_content=b"pdf content",
                filename="test.pdf",
                content_type="application/pdf",
                meeting_id=uuid.uuid4(),
                agenda_item_id=uuid.uuid4(),
                storage=storage,
            )

    @pytest.mark.asyncio
    async def test_no_parent_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with pytest.raises(ValueError, match="Exactly one of meeting_id or agenda_item_id"):
            await upload_attachment(
                session,
                file_content=b"pdf content",
                filename="test.pdf",
                content_type="application/pdf",
                storage=storage,
            )

    @pytest.mark.asyncio
    async def test_valid_mime_invalid_extension_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with pytest.raises(ValueError, match="Unsupported file format"):
            await upload_attachment(
                session,
                file_content=b"binary",
                filename="malware.exe",
                content_type="application/pdf",
                meeting_id=uuid.uuid4(),
                storage=storage,
            )


class TestDownloadAttachment:
    @pytest.mark.asyncio
    async def test_downloads_file(self) -> None:
        session = AsyncMock()
        att = _mock_attachment()
        storage = AsyncMock()
        storage.load = AsyncMock(return_value=b"file bytes")

        with patch(
            "voter_api.services.meeting_attachment_service.get_attachment",
            new_callable=AsyncMock,
            return_value=att,
        ):
            content, metadata = await download_attachment(session, att.id, storage)

        assert content == b"file bytes"
        assert metadata is att

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()
        storage = AsyncMock()

        with (
            patch(
                "voter_api.services.meeting_attachment_service.get_attachment",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await download_attachment(session, uuid.uuid4(), storage)


class TestDeleteAttachment:
    @pytest.mark.asyncio
    async def test_soft_deletes(self) -> None:
        session = AsyncMock()
        att = _mock_attachment()

        with patch(
            "voter_api.services.meeting_attachment_service.get_attachment",
            new_callable=AsyncMock,
            return_value=att,
        ):
            await delete_attachment(session, att.id)

        assert att.deleted_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.meeting_attachment_service.get_attachment",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await delete_attachment(session, uuid.uuid4())
