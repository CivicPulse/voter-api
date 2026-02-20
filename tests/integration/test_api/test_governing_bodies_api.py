"""Integration tests for governing bodies API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.governing_bodies import governing_bodies_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    """Create a mock user with the given role."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_type() -> MagicMock:
    """Create a mock GoverningBodyType."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.name = "County Commission"
    t.slug = "county-commission"
    t.description = None
    t.is_default = True
    t.created_at = datetime.now(UTC)
    return t


def _mock_body(**overrides) -> MagicMock:
    """Create a mock GoverningBody."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Fulton County Commission",
        "type": _mock_type(),
        "type_id": uuid.uuid4(),
        "jurisdiction": "Fulton County",
        "description": "County governing body",
        "website_url": "https://example.com",
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


@pytest.fixture
def admin_user() -> MagicMock:
    return _mock_user("admin")


@pytest.fixture
def viewer_user() -> MagicMock:
    return _mock_user("viewer")


@pytest.fixture
def admin_app(admin_user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(governing_bodies_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def viewer_app(viewer_user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(governing_bodies_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    return app


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=viewer_app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


class TestListGoverningBodies:
    """Tests for GET /api/v1/governing-bodies."""

    @pytest.mark.asyncio
    async def test_returns_paginated_list(self, admin_client: AsyncClient) -> None:
        """Returns 200 with paginated results."""
        bodies = [_mock_body(), _mock_body(name="DeKalb County")]
        with patch(
            "voter_api.api.v1.governing_bodies.list_bodies",
            new_callable=AsyncMock,
            return_value=(bodies, 2),
        ):
            resp = await admin_client.get("/api/v1/governing-bodies")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        assert data["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_filter_by_type_id(self, admin_client: AsyncClient) -> None:
        """Accepts type_id query parameter."""
        with patch(
            "voter_api.api.v1.governing_bodies.list_bodies",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await admin_client.get(f"/api/v1/governing-bodies?type_id={uuid.uuid4()}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_filter_by_jurisdiction(self, admin_client: AsyncClient) -> None:
        """Accepts jurisdiction query parameter."""
        with patch(
            "voter_api.api.v1.governing_bodies.list_bodies",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await admin_client.get("/api/v1/governing-bodies?jurisdiction=Fulton")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, viewer_client: AsyncClient) -> None:
        """Viewers can list bodies."""
        with patch(
            "voter_api.api.v1.governing_bodies.list_bodies",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await viewer_client.get("/api/v1/governing-bodies")
        assert resp.status_code == 200


class TestCreateGoverningBody:
    """Tests for POST /api/v1/governing-bodies."""

    @pytest.mark.asyncio
    async def test_admin_creates_body(self, admin_client: AsyncClient) -> None:
        """Admin can create a governing body."""
        body = _mock_body()
        with (
            patch(
                "voter_api.api.v1.governing_bodies.create_body",
                new_callable=AsyncMock,
                return_value=body,
            ),
            patch(
                "voter_api.api.v1.governing_bodies.get_meeting_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            resp = await admin_client.post(
                "/api/v1/governing-bodies",
                json={
                    "name": "Fulton County Commission",
                    "type_id": str(body.type_id),
                    "jurisdiction": "Fulton County",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Fulton County Commission"

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        """Viewer gets 403 on create."""
        resp = await viewer_client.post(
            "/api/v1/governing-bodies",
            json={
                "name": "Test",
                "type_id": str(uuid.uuid4()),
                "jurisdiction": "Test County",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_returns_409(self, admin_client: AsyncClient) -> None:
        """Duplicate name+jurisdiction returns 409."""
        with patch(
            "voter_api.api.v1.governing_bodies.create_body",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            resp = await admin_client.post(
                "/api/v1/governing-bodies",
                json={
                    "name": "Dupe",
                    "type_id": str(uuid.uuid4()),
                    "jurisdiction": "Dupe County",
                },
            )
        assert resp.status_code == 409


class TestGetGoverningBody:
    """Tests for GET /api/v1/governing-bodies/{id}."""

    @pytest.mark.asyncio
    async def test_returns_detail(self, admin_client: AsyncClient) -> None:
        """Returns body detail with meeting count."""
        body = _mock_body()
        with (
            patch(
                "voter_api.api.v1.governing_bodies.get_body",
                new_callable=AsyncMock,
                return_value=body,
            ),
            patch(
                "voter_api.api.v1.governing_bodies.get_meeting_count",
                new_callable=AsyncMock,
                return_value=5,
            ),
        ):
            resp = await admin_client.get(f"/api/v1/governing-bodies/{body.id}")
        assert resp.status_code == 200
        assert resp.json()["meeting_count"] == 5

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        """Non-existent body returns 404."""
        with patch(
            "voter_api.api.v1.governing_bodies.get_body",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/governing-bodies/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateGoverningBody:
    """Tests for PATCH /api/v1/governing-bodies/{id}."""

    @pytest.mark.asyncio
    async def test_admin_updates_body(self, admin_client: AsyncClient) -> None:
        """Admin can update a governing body."""
        body = _mock_body(name="Updated Name")
        with (
            patch(
                "voter_api.api.v1.governing_bodies.update_body",
                new_callable=AsyncMock,
                return_value=body,
            ),
            patch(
                "voter_api.api.v1.governing_bodies.get_meeting_count",
                new_callable=AsyncMock,
                return_value=0,
            ),
        ):
            resp = await admin_client.patch(
                f"/api/v1/governing-bodies/{body.id}",
                json={"name": "Updated Name"},
            )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_viewer_cannot_update(self, viewer_client: AsyncClient) -> None:
        """Viewer gets 403 on update."""
        resp = await viewer_client.patch(
            f"/api/v1/governing-bodies/{uuid.uuid4()}",
            json={"name": "New Name"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        """Non-existent body returns 404."""
        with patch(
            "voter_api.api.v1.governing_bodies.update_body",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            resp = await admin_client.patch(
                f"/api/v1/governing-bodies/{uuid.uuid4()}",
                json={"name": "X"},
            )
        assert resp.status_code == 404


class TestDeleteGoverningBody:
    """Tests for DELETE /api/v1/governing-bodies/{id}."""

    @pytest.mark.asyncio
    async def test_admin_deletes_body(self, admin_client: AsyncClient) -> None:
        """Admin can soft-delete a governing body."""
        with patch(
            "voter_api.api.v1.governing_bodies.delete_body",
            new_callable=AsyncMock,
        ):
            resp = await admin_client.delete(f"/api/v1/governing-bodies/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, viewer_client: AsyncClient) -> None:
        """Viewer gets 403 on delete."""
        resp = await viewer_client.delete(f"/api/v1/governing-bodies/{uuid.uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        """Non-existent body returns 404."""
        with patch(
            "voter_api.api.v1.governing_bodies.delete_body",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            resp = await admin_client.delete(f"/api/v1/governing-bodies/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_with_active_meetings_returns_409(self, admin_client: AsyncClient) -> None:
        """Body with active meetings returns 409."""
        with patch(
            "voter_api.api.v1.governing_bodies.delete_body",
            new_callable=AsyncMock,
            side_effect=ValueError("Cannot delete governing body with active meetings"),
        ):
            resp = await admin_client.delete(f"/api/v1/governing-bodies/{uuid.uuid4()}")
        assert resp.status_code == 409
