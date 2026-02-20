"""Integration tests for GET /geocoding/point-lookup endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.core.dependencies import get_async_session


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Create a minimal FastAPI app with geocoding router."""
    app = FastAPI()
    app.include_router(geocoding_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)


class TestPointLookupEndpoint:
    """Tests for GET /api/v1/geocoding/point-lookup."""

    @pytest.mark.asyncio
    async def test_valid_coords_returns_200(self, client) -> None:
        """Valid Georgia coords return 200 with districts list."""
        with patch(
            "voter_api.api.v1.geocoding.find_boundaries_at_point",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388")

        assert resp.status_code == 200
        data = resp.json()
        assert "latitude" in data
        assert "longitude" in data
        assert "districts" in data
        assert isinstance(data["districts"], list)

    @pytest.mark.asyncio
    async def test_out_of_georgia_returns_422(self, client) -> None:
        """Coordinates outside Georgia return 422."""
        resp = await client.get("/api/v1/geocoding/point-lookup?lat=40.7128&lng=-74.0060")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_accuracy_over_100_returns_422(self, client) -> None:
        """Accuracy > 100 meters returns 422."""
        resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388&accuracy=150")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_params_returns_422(self, client) -> None:
        """Missing lat or lng returns 422."""
        resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_districts_returns_200(self, client) -> None:
        """Coords with no matching boundaries return 200 with empty districts."""
        with patch(
            "voter_api.api.v1.geocoding.find_boundaries_at_point",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/geocoding/point-lookup?lat=31.0&lng=-83.0")

        assert resp.status_code == 200
        data = resp.json()
        assert data["districts"] == []

    @pytest.mark.asyncio
    async def test_anonymous_access_allowed(self, client) -> None:
        """Anonymous (unauthenticated) requests are allowed — endpoint is public."""
        with patch(
            "voter_api.api.v1.geocoding.find_boundaries_at_point",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_with_accuracy_returns_200(self, client) -> None:
        """Valid accuracy parameter returns 200."""
        with patch(
            "voter_api.api.v1.geocoding.find_boundaries_at_point",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388&accuracy=50")

        assert resp.status_code == 200
        data = resp.json()
        assert data["accuracy"] == 50.0
