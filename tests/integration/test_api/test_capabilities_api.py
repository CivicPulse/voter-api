"""Integration tests for GET /api/v1/elections/capabilities endpoint."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elections import elections_router

from .conftest import make_test_app


@pytest.fixture
def app(mock_session):
    return make_test_app(elections_router, mock_session)


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        follow_redirects=False,
    ) as c:
        yield c


class TestCapabilitiesEndpoint:
    """Tests for the capabilities discovery endpoint."""

    async def test_capabilities_returns_200(self, client):
        """GET /capabilities returns 200 OK."""
        resp = await client.get("/api/v1/elections/capabilities")
        assert resp.status_code == 200

    async def test_capabilities_response_body(self, client):
        """Response body matches contract: supported_filters + endpoints."""
        resp = await client.get("/api/v1/elections/capabilities")
        data = resp.json()
        assert data["supported_filters"] == [
            "q",
            "race_category",
            "county",
            "district",
            "election_date",
        ]
        assert data["endpoints"] == {"filter_options": True}

    async def test_capabilities_cache_control(self, client):
        """Response has Cache-Control: public, max-age=3600."""
        resp = await client.get("/api/v1/elections/capabilities")
        assert resp.headers.get("cache-control") == "public, max-age=3600"

    async def test_capabilities_not_shadowed_by_election_id(self, client):
        """
        /capabilities must NOT return 422 (UUID validation error).
        If route ordering is wrong, FastAPI treats 'capabilities' as an
        election_id UUID parameter and returns 422.
        """
        resp = await client.get("/api/v1/elections/capabilities")
        assert resp.status_code != 422
        assert resp.status_code == 200


class TestExistingEndpointsUnchanged:
    """Regression tests: existing election endpoints still work after /capabilities is added."""

    @pytest.mark.parametrize(
        "method,path,expected_status",
        [
            ("GET", "/api/v1/elections", 200),
            ("GET", f"/api/v1/elections/{uuid.uuid4()}", 404),
        ],
        ids=["list_elections", "get_election_404"],
    )
    async def test_existing_endpoint(self, client, method, path, expected_status):
        """Existing election endpoints return expected status codes."""
        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
        ) as mock_list:
            mock_list.return_value = ([], 0)
            with patch(
                "voter_api.services.election_service.get_election_by_id",
                new_callable=AsyncMock,
            ) as mock_get:
                mock_get.return_value = None
                resp = await client.request(method, path)
                assert resp.status_code == expected_status
