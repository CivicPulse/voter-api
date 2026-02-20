"""Integration tests for agenda items API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.agenda_items import agenda_items_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_item(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "title": "Budget Approval",
        "description": "Review Q2 budget",
        "action_taken": None,
        "disposition": "approved",
        "display_order": 10,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_app(user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(agenda_items_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.fixture
async def admin_client() -> AsyncClient:
    transport = ASGITransport(app=_make_app(_mock_user("admin")))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def viewer_client() -> AsyncClient:
    transport = ASGITransport(app=_make_app(_mock_user("viewer")))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def contributor_client() -> AsyncClient:
    transport = ASGITransport(app=_make_app(_mock_user("contributor")))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


MEETING_ID = uuid.uuid4()


class TestListAgendaItems:
    @pytest.mark.asyncio
    async def test_returns_list(self, admin_client: AsyncClient) -> None:
        items = [_mock_item(meeting_id=MEETING_ID)]
        with (
            patch(
                "voter_api.api.v1.agenda_items.list_items",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{MEETING_ID}/agenda-items")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_meeting_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.agenda_items.list_items",
            new_callable=AsyncMock,
            side_effect=ValueError("Meeting not found"),
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{uuid.uuid4()}/agenda-items")
        assert resp.status_code == 404


class TestCreateAgendaItem:
    @pytest.mark.asyncio
    async def test_admin_creates(self, admin_client: AsyncClient) -> None:
        item = _mock_item(meeting_id=MEETING_ID)
        with (
            patch(
                "voter_api.api.v1.agenda_items.create_item",
                new_callable=AsyncMock,
                return_value=item,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{MEETING_ID}/agenda-items",
                json={"title": "New Item"},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_contributor_creates(self, contributor_client: AsyncClient) -> None:
        item = _mock_item(meeting_id=MEETING_ID)
        with (
            patch(
                "voter_api.api.v1.agenda_items.create_item",
                new_callable=AsyncMock,
                return_value=item,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            resp = await contributor_client.post(
                f"/api/v1/meetings/{MEETING_ID}/agenda-items",
                json={"title": "New Item"},
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            f"/api/v1/meetings/{MEETING_ID}/agenda-items",
            json={"title": "New Item"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_title_returns_422(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.post(
            f"/api/v1/meetings/{MEETING_ID}/agenda-items",
            json={"title": ""},
        )
        assert resp.status_code == 422


class TestGetAgendaItem:
    @pytest.mark.asyncio
    async def test_returns_detail(self, admin_client: AsyncClient) -> None:
        item = _mock_item(meeting_id=MEETING_ID)
        with (
            patch(
                "voter_api.api.v1.agenda_items.get_item",
                new_callable=AsyncMock,
                return_value=item,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(2, 1),
            ),
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{MEETING_ID}/agenda-items/{item.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_count"] == 2
        assert data["video_embed_count"] == 1

    @pytest.mark.asyncio
    async def test_not_found(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.agenda_items.get_item",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{MEETING_ID}/agenda-items/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateAgendaItem:
    @pytest.mark.asyncio
    async def test_admin_updates(self, admin_client: AsyncClient) -> None:
        item = _mock_item(meeting_id=MEETING_ID, disposition="tabled")
        with (
            patch(
                "voter_api.api.v1.agenda_items.update_item",
                new_callable=AsyncMock,
                return_value=item,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            resp = await admin_client.patch(
                f"/api/v1/meetings/{MEETING_ID}/agenda-items/{item.id}",
                json={"disposition": "tabled"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_cannot_update(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.patch(
            f"/api/v1/meetings/{MEETING_ID}/agenda-items/{uuid.uuid4()}",
            json={"title": "Updated"},
        )
        assert resp.status_code == 403


class TestDeleteAgendaItem:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.agenda_items.delete_item",
            new_callable=AsyncMock,
        ):
            resp = await admin_client.delete(f"/api/v1/meetings/{MEETING_ID}/agenda-items/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.delete(f"/api/v1/meetings/{MEETING_ID}/agenda-items/{uuid.uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_contributor_cannot_delete(self, contributor_client: AsyncClient) -> None:
        resp = await contributor_client.delete(f"/api/v1/meetings/{MEETING_ID}/agenda-items/{uuid.uuid4()}")
        assert resp.status_code == 403


class TestReorderAgendaItems:
    @pytest.mark.asyncio
    async def test_admin_reorders(self, admin_client: AsyncClient) -> None:
        items = [
            _mock_item(meeting_id=MEETING_ID, display_order=10),
            _mock_item(meeting_id=MEETING_ID, display_order=20),
        ]
        with (
            patch(
                "voter_api.api.v1.agenda_items.reorder_items",
                new_callable=AsyncMock,
                return_value=items,
            ),
            patch(
                "voter_api.api.v1.agenda_items.get_item_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0),
            ),
        ):
            resp = await admin_client.put(
                f"/api/v1/meetings/{MEETING_ID}/agenda-items/reorder",
                json={"item_ids": [str(items[1].id), str(items[0].id)]},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_viewer_cannot_reorder(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.put(
            f"/api/v1/meetings/{MEETING_ID}/agenda-items/reorder",
            json={"item_ids": [str(uuid.uuid4())]},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_list_returns_422(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.put(
            f"/api/v1/meetings/{MEETING_ID}/agenda-items/reorder",
            json={"item_ids": []},
        )
        assert resp.status_code == 422
