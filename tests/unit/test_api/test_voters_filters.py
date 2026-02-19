"""Unit tests for GET /api/v1/voters/filters endpoint."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.voters import voters_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user() -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testuser"
    user.role = "viewer"
    user.is_active = True
    return user


_FILTER_OPTIONS = {
    "statuses": ["A", "I"],
    "counties": ["COBB", "FULTON"],
    "congressional_districts": ["05", "06"],
    "state_senate_districts": ["34"],
    "state_house_districts": ["55"],
}


@pytest.fixture
def app() -> FastAPI:
    """Create minimal FastAPI app with voters router and mocked deps."""
    test_app = FastAPI()
    test_app.include_router(voters_router, prefix="/api/v1")
    test_app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return test_app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def unauthenticated_app() -> FastAPI:
    """Create app without get_current_user override to test auth enforcement."""
    test_app = FastAPI()
    test_app.include_router(voters_router, prefix="/api/v1")
    test_app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    return test_app


@pytest.fixture
def unauthenticated_client(unauthenticated_app: FastAPI) -> AsyncClient:
    """Create async test client without auth."""
    return AsyncClient(transport=ASGITransport(app=unauthenticated_app), base_url="http://test")


class TestGetVoterFilterOptions:
    """Tests for GET /api/v1/voters/filters."""

    @pytest.mark.asyncio
    async def test_returns_correct_response_structure(self, client: AsyncClient) -> None:
        """Endpoint returns all five filter keys."""
        with patch(
            "voter_api.api.v1.voters.get_voter_filter_options",
            new_callable=AsyncMock,
            return_value=_FILTER_OPTIONS,
        ):
            resp = await client.get("/api/v1/voters/filters")

        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {
            "statuses",
            "counties",
            "congressional_districts",
            "state_senate_districts",
            "state_house_districts",
        }

    @pytest.mark.asyncio
    async def test_returns_correct_values(self, client: AsyncClient) -> None:
        """Endpoint serializes service return values correctly."""
        with patch(
            "voter_api.api.v1.voters.get_voter_filter_options",
            new_callable=AsyncMock,
            return_value=_FILTER_OPTIONS,
        ):
            resp = await client.get("/api/v1/voters/filters")

        data = resp.json()
        assert data["statuses"] == ["A", "I"]
        assert data["counties"] == ["COBB", "FULTON"]
        assert data["congressional_districts"] == ["05", "06"]
        assert data["state_senate_districts"] == ["34"]
        assert data["state_house_districts"] == ["55"]

    @pytest.mark.asyncio
    async def test_returns_empty_lists_when_no_data(self, client: AsyncClient) -> None:
        """Endpoint handles empty filter options gracefully."""
        empty_options = {
            "statuses": [],
            "counties": [],
            "congressional_districts": [],
            "state_senate_districts": [],
            "state_house_districts": [],
        }
        with patch(
            "voter_api.api.v1.voters.get_voter_filter_options",
            new_callable=AsyncMock,
            return_value=empty_options,
        ):
            resp = await client.get("/api/v1/voters/filters")

        assert resp.status_code == 200
        data = resp.json()
        assert data["statuses"] == []
        assert data["counties"] == []
        assert data["congressional_districts"] == []
        assert data["state_senate_districts"] == []
        assert data["state_house_districts"] == []

    @pytest.mark.asyncio
    async def test_requires_authentication(self, unauthenticated_client: AsyncClient) -> None:
        """Endpoint returns 401 when no Bearer token is provided."""
        resp = await unauthenticated_client.get("/api/v1/voters/filters")

        assert resp.status_code == 401
