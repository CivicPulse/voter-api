"""Integration tests for governing body types API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.governing_body_types import governing_body_types_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    """Create a mock user with the given role."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_type(**overrides) -> MagicMock:
    """Create a mock GoverningBodyType."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "County Commission",
        "slug": "county-commission",
        "description": None,
        "is_default": True,
        "created_at": datetime.now(UTC),
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
def contributor_user() -> MagicMock:
    return _mock_user("contributor")


@pytest.fixture
def admin_app(admin_user: MagicMock) -> FastAPI:
    """App with admin auth."""
    app = FastAPI()
    app.include_router(governing_body_types_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


@pytest.fixture
def viewer_app(viewer_user: MagicMock) -> FastAPI:
    """App with viewer auth."""
    app = FastAPI()
    app.include_router(governing_body_types_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    return app


@pytest.fixture
def contributor_app(contributor_user: MagicMock) -> FastAPI:
    """App with contributor auth."""
    app = FastAPI()
    app.include_router(governing_body_types_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: contributor_user
    return app


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=viewer_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def contributor_client(contributor_app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=contributor_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestListGoverningBodyTypes:
    """Tests for GET /api/v1/governing-body-types."""

    @pytest.mark.asyncio
    async def test_returns_types_list(self, admin_client: AsyncClient) -> None:
        """List endpoint returns 200 with items."""
        types = [_mock_type(), _mock_type(name="City Council", slug="city-council")]
        with patch(
            "voter_api.api.v1.governing_body_types.list_types",
            new_callable=AsyncMock,
            return_value=types,
        ):
            resp = await admin_client.get("/api/v1/governing-body-types")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, viewer_client: AsyncClient) -> None:
        """Viewers can list types."""
        with patch(
            "voter_api.api.v1.governing_body_types.list_types",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await viewer_client.get("/api/v1/governing-body-types")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_contributor_can_list(self, contributor_client: AsyncClient) -> None:
        """Contributors can list types."""
        with patch(
            "voter_api.api.v1.governing_body_types.list_types",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await contributor_client.get("/api/v1/governing-body-types")
        assert resp.status_code == 200


class TestCreateGoverningBodyType:
    """Tests for POST /api/v1/governing-body-types."""

    @pytest.mark.asyncio
    async def test_admin_creates_type(self, admin_client: AsyncClient) -> None:
        """Admin can create a new type."""
        new_type = _mock_type(name="Housing Authority", slug="housing-authority", is_default=False)
        with patch(
            "voter_api.api.v1.governing_body_types.create_type",
            new_callable=AsyncMock,
            return_value=new_type,
        ):
            resp = await admin_client.post(
                "/api/v1/governing-body-types",
                json={"name": "Housing Authority"},
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Housing Authority"

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        """Viewer gets 403 on create."""
        resp = await viewer_client.post(
            "/api/v1/governing-body-types",
            json={"name": "Something"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_contributor_cannot_create(self, contributor_client: AsyncClient) -> None:
        """Contributor gets 403 on create."""
        resp = await contributor_client.post(
            "/api/v1/governing-body-types",
            json={"name": "Something"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_duplicate_returns_409(self, admin_client: AsyncClient) -> None:
        """Duplicate name returns 409."""
        with patch(
            "voter_api.api.v1.governing_body_types.create_type",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            resp = await admin_client.post(
                "/api/v1/governing-body-types",
                json={"name": "County Commission"},
            )
        assert resp.status_code == 409
