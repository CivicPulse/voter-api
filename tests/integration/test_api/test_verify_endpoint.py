"""Integration tests for GET /geocoding/verify endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.core.dependencies import get_async_session
from voter_api.schemas.geocoding import (
    AddressSuggestion,
    AddressVerifyResponse,
    MalformedComponent,
    ValidationDetail,
)


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


class TestVerifyEndpoint:
    """Tests for GET /api/v1/geocoding/verify."""

    @pytest.mark.asyncio
    async def test_valid_address_returns_200(self, client) -> None:
        """Valid address returns 200 with verification data."""
        verify_response = AddressVerifyResponse(
            input_address="100 Peachtree St NW, Atlanta, GA 30303",
            normalized_address="100 PEACHTREE ST NW ATLANTA GA 30303",
            is_well_formed=True,
            validation=ValidationDetail(
                present_components=[
                    "street_number",
                    "street_name",
                    "street_type",
                    "post_direction",
                    "city",
                    "state",
                    "zip",
                ],
                missing_components=[],
                malformed_components=[],
            ),
            suggestions=[
                AddressSuggestion(
                    address="100 PEACHTREE ST NW ATLANTA GA 30303",
                    latitude=33.7589985,
                    longitude=-84.3879824,
                    confidence_score=1.0,
                ),
            ],
        )
        with patch(
            "voter_api.api.v1.geocoding.verify_address",
            new_callable=AsyncMock,
            return_value=verify_response,
        ):
            resp = await client.get("/api/v1/geocoding/verify?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()
        assert data["input_address"] == "100 Peachtree St NW, Atlanta, GA 30303"
        assert data["normalized_address"] == "100 PEACHTREE ST NW ATLANTA GA 30303"
        assert data["is_well_formed"] is True
        assert "validation" in data
        assert "suggestions" in data
        assert len(data["suggestions"]) == 1

    @pytest.mark.asyncio
    async def test_partial_address_returns_200_with_missing(self, client) -> None:
        """Partial address returns 200 with missing components flagged."""
        verify_response = AddressVerifyResponse(
            input_address="100 Peachtree",
            normalized_address="100 PEACHTREE",
            is_well_formed=False,
            validation=ValidationDetail(
                present_components=["street_number", "street_name"],
                missing_components=["city", "state", "zip"],
                malformed_components=[],
            ),
            suggestions=[],
        )
        with patch(
            "voter_api.api.v1.geocoding.verify_address",
            new_callable=AsyncMock,
            return_value=verify_response,
        ):
            resp = await client.get("/api/v1/geocoding/verify?address=100+Peachtree")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_well_formed"] is False
        assert "city" in data["validation"]["missing_components"]
        assert "state" in data["validation"]["missing_components"]
        assert "zip" in data["validation"]["missing_components"]

    @pytest.mark.asyncio
    async def test_malformed_zip_returns_200_with_malformed(self, client) -> None:
        """Address with bad ZIP returns 200 with malformed component."""
        verify_response = AddressVerifyResponse(
            input_address="100 Main St, Atlanta, GA ABCDE",
            normalized_address="100 MAIN ST ATLANTA GA ABCDE",
            is_well_formed=False,
            validation=ValidationDetail(
                present_components=["street_number", "street_name", "city", "state", "zip"],
                missing_components=[],
                malformed_components=[
                    MalformedComponent(component="zip", issue="ZIP code must be 5 digits or ZIP+4 format"),
                ],
            ),
            suggestions=[],
        )
        with patch(
            "voter_api.api.v1.geocoding.verify_address",
            new_callable=AsyncMock,
            return_value=verify_response,
        ):
            resp = await client.get("/api/v1/geocoding/verify?address=100+Main+St,+Atlanta,+GA+ABCDE")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_well_formed"] is False
        assert len(data["validation"]["malformed_components"]) == 1
        assert data["validation"]["malformed_components"][0]["component"] == "zip"

    @pytest.mark.asyncio
    async def test_empty_address_returns_422(self, client) -> None:
        """Empty address returns 422 validation error."""
        resp = await client.get("/api/v1/geocoding/verify?address=")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_422(self, client) -> None:
        """Whitespace-only address returns 422."""
        resp = await client.get("/api/v1/geocoding/verify?address=%20%20%20")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_address_too_long_returns_422(self, client) -> None:
        """Address exceeding 500 chars returns 422."""
        long_addr = "A" * 501
        resp = await client.get(f"/api/v1/geocoding/verify?address={long_addr}")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_anonymous_access_allowed(self, client) -> None:
        """Anonymous (unauthenticated) requests are allowed — endpoint is public."""
        verify_response = AddressVerifyResponse(
            input_address="100 Main St",
            normalized_address="100 MAIN ST",
            is_well_formed=False,
            validation=ValidationDetail(
                present_components=["street_number", "street_name"],
                missing_components=["city", "state", "zip"],
                malformed_components=[],
            ),
            suggestions=[],
        )
        with patch(
            "voter_api.api.v1.geocoding.verify_address",
            new_callable=AsyncMock,
            return_value=verify_response,
        ):
            resp = await client.get("/api/v1/geocoding/verify?address=100+Main+St")
        assert resp.status_code == 200
