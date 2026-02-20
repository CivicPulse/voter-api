"""Integration tests for attachments API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.attachments import attachments_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_attachment(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "agenda_item_id": None,
        "original_filename": "budget.pdf",
        "stored_path": "2026/02/abc.pdf",
        "file_size": 1024,
        "content_type": "application/pdf",
        "download_url": None,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_app(user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(attachments_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.fixture
async def admin_client() -> AsyncClient:
    transport = ASGITransport(app=_make_app(_mock_user("admin")))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


@pytest.fixture
async def viewer_client() -> AsyncClient:
    transport = ASGITransport(app=_make_app(_mock_user("viewer")))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


MEETING_ID = uuid.uuid4()


class TestListMeetingAttachments:
    @pytest.mark.asyncio
    async def test_returns_list(self, admin_client: AsyncClient) -> None:
        attachments = [_mock_attachment(meeting_id=MEETING_ID)]
        with patch(
            "voter_api.api.v1.attachments.list_attachments",
            new_callable=AsyncMock,
            return_value=attachments,
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{MEETING_ID}/attachments")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["download_url"] is not None


class TestUploadMeetingAttachment:
    @pytest.mark.asyncio
    async def test_admin_uploads(self, admin_client: AsyncClient) -> None:
        att = _mock_attachment(meeting_id=MEETING_ID)
        with patch(
            "voter_api.api.v1.attachments.upload_attachment",
            new_callable=AsyncMock,
            return_value=att,
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{MEETING_ID}/attachments",
                files={"file": ("budget.pdf", b"fake content", "application/pdf")},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_viewer_cannot_upload(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            f"/api/v1/meetings/{MEETING_ID}/attachments",
            files={"file": ("test.pdf", b"content", "application/pdf")},
        )
        assert resp.status_code == 403


class TestGetAttachment:
    @pytest.mark.asyncio
    async def test_returns_metadata(self, admin_client: AsyncClient) -> None:
        att = _mock_attachment()
        with patch(
            "voter_api.api.v1.attachments.get_attachment",
            new_callable=AsyncMock,
            return_value=att,
        ):
            resp = await admin_client.get(f"/api/v1/attachments/{att.id}")
        assert resp.status_code == 200
        assert resp.json()["original_filename"] == "budget.pdf"

    @pytest.mark.asyncio
    async def test_not_found(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.attachments.get_attachment",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/attachments/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestDownloadAttachment:
    @pytest.mark.asyncio
    async def test_downloads_with_headers(self, admin_client: AsyncClient) -> None:
        att = _mock_attachment()
        with patch(
            "voter_api.api.v1.attachments.download_attachment",
            new_callable=AsyncMock,
            return_value=(b"file bytes", att),
        ):
            resp = await admin_client.get(f"/api/v1/attachments/{att.id}/download")
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers
        assert "budget.pdf" in resp.headers["Content-Disposition"]


class TestDeleteAttachment:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.attachments.delete_attachment",
            new_callable=AsyncMock,
        ):
            resp = await admin_client.delete(f"/api/v1/attachments/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.delete(f"/api/v1/attachments/{uuid.uuid4()}")
        assert resp.status_code == 403
