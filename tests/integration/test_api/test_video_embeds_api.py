"""Integration tests for video embeds API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.video_embeds import video_embeds_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_embed(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "agenda_item_id": None,
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "platform": "youtube",
        "start_seconds": None,
        "end_seconds": None,
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
    app.include_router(video_embeds_router, prefix="/api/v1")
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
AGENDA_ITEM_ID = uuid.uuid4()


class TestListMeetingVideoEmbeds:
    @pytest.mark.asyncio
    async def test_returns_list(self, admin_client: AsyncClient) -> None:
        embeds = [_mock_embed(meeting_id=MEETING_ID)]
        with patch(
            "voter_api.api.v1.video_embeds.list_embeds",
            new_callable=AsyncMock,
            return_value=embeds,
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{MEETING_ID}/video-embeds")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1


class TestCreateMeetingVideoEmbed:
    @pytest.mark.asyncio
    async def test_admin_creates(self, admin_client: AsyncClient) -> None:
        embed = _mock_embed(meeting_id=MEETING_ID)
        with patch(
            "voter_api.api.v1.video_embeds.create_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{MEETING_ID}/video-embeds",
                json={"video_url": "https://www.youtube.com/watch?v=abc"},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_url_returns_422(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.video_embeds.create_embed",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid video URL. Must be a YouTube or Vimeo URL."),
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{MEETING_ID}/video-embeds",
                json={"video_url": "https://example.com/nope"},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            f"/api/v1/meetings/{MEETING_ID}/video-embeds",
            json={"video_url": "https://youtube.com/watch?v=x"},
        )
        assert resp.status_code == 403


class TestCreateAgendaItemVideoEmbed:
    @pytest.mark.asyncio
    async def test_creates_for_agenda_item(self, admin_client: AsyncClient) -> None:
        embed = _mock_embed(agenda_item_id=AGENDA_ITEM_ID, meeting_id=None)
        with patch(
            "voter_api.api.v1.video_embeds.create_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{MEETING_ID}/agenda-items/{AGENDA_ITEM_ID}/video-embeds",
                json={"video_url": "https://vimeo.com/123"},
            )
        assert resp.status_code == 201


class TestGetVideoEmbed:
    @pytest.mark.asyncio
    async def test_returns_detail(self, admin_client: AsyncClient) -> None:
        embed = _mock_embed()
        with patch(
            "voter_api.api.v1.video_embeds.get_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            resp = await admin_client.get(f"/api/v1/video-embeds/{embed.id}")
        assert resp.status_code == 200
        assert resp.json()["platform"] == "youtube"

    @pytest.mark.asyncio
    async def test_not_found(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.video_embeds.get_embed",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/video-embeds/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateVideoEmbed:
    @pytest.mark.asyncio
    async def test_admin_updates(self, admin_client: AsyncClient) -> None:
        embed = _mock_embed(start_seconds=30)
        with patch(
            "voter_api.api.v1.video_embeds.update_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            resp = await admin_client.patch(
                f"/api/v1/video-embeds/{embed.id}",
                json={"start_seconds": 30},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_cannot_update(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.patch(
            f"/api/v1/video-embeds/{uuid.uuid4()}",
            json={"start_seconds": 10},
        )
        assert resp.status_code == 403


class TestDeleteVideoEmbed:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.video_embeds.delete_embed",
            new_callable=AsyncMock,
        ):
            resp = await admin_client.delete(f"/api/v1/video-embeds/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.delete(f"/api/v1/video-embeds/{uuid.uuid4()}")
        assert resp.status_code == 403
