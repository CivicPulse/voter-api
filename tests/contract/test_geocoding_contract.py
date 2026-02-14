"""Contract tests for geocoding endpoints against OpenAPI schema."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.schemas.geocoding import (
    AddressGeocodeResponse,
    AddressSuggestion,
    AddressVerifyResponse,
    GeocodeMetadata,
    ValidationDetail,
)


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.role = "analyst"
    user.id = "test-user-id"
    return user


@pytest.fixture
def app(mock_session, mock_user) -> FastAPI:
    """Create a minimal FastAPI app with geocoding router."""
    app = FastAPI()
    app.include_router(geocoding_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_user
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)


class TestGeocodeContractResponse:
    """Contract tests for GET /geocoding/geocode 200 response."""

    @pytest.mark.asyncio
    async def test_200_response_matches_schema(self, client) -> None:
        """200 response matches AddressGeocodeResponse schema."""
        mock_response = AddressGeocodeResponse(
            formatted_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
            latitude=33.7589985,
            longitude=-84.3879824,
            confidence=1.0,
            metadata=GeocodeMetadata(cached=False, provider="census"),
        )
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()

        # Required fields per OpenAPI spec
        assert isinstance(data["formatted_address"], str)
        assert isinstance(data["latitude"], float)
        assert isinstance(data["longitude"], float)
        assert "confidence" in data
        assert isinstance(data["metadata"], dict)
        assert "cached" in data["metadata"]
        assert isinstance(data["metadata"]["cached"], bool)
        assert "provider" in data["metadata"]
        assert isinstance(data["metadata"]["provider"], str)

    @pytest.mark.asyncio
    async def test_404_response_has_detail(self, client) -> None:
        """404 response includes detail message."""
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=99999+Nonexistent+Rd,+Nowhere,+GA+00000")

        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
        assert isinstance(data["detail"], str)

    @pytest.mark.asyncio
    async def test_422_response_on_empty_address(self, client) -> None:
        """422 response on empty address."""
        resp = await client.get("/api/v1/geocoding/geocode?address=")
        assert resp.status_code == 422


class TestPointLookupContractResponse:
    """Contract tests for GET /geocoding/point-lookup 200 response."""

    @pytest.mark.asyncio
    async def test_200_response_matches_schema(self, client) -> None:
        """200 response matches PointLookupResponse schema."""
        with patch(
            "voter_api.api.v1.geocoding.find_boundaries_at_point",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["latitude"], float)
        assert isinstance(data["longitude"], float)
        assert "districts" in data
        assert isinstance(data["districts"], list)


class TestVerifyContractResponse:
    """Contract tests for GET /geocoding/verify 200 response."""

    @pytest.mark.asyncio
    async def test_200_response_matches_schema(self, client) -> None:
        """200 response matches AddressVerifyResponse schema."""
        mock_response = AddressVerifyResponse(
            input_address="100 Peachtree St NW, Atlanta, GA 30303",
            normalized_address="100 PEACHTREE ST NW ATLANTA GA 30303",
            is_well_formed=True,
            validation=ValidationDetail(
                present_components=["street_number", "street_name", "city", "state", "zip"],
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
            return_value=mock_response,
        ):
            resp = await client.get("/api/v1/geocoding/verify?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()

        # Required fields per OpenAPI spec
        assert isinstance(data["input_address"], str)
        assert isinstance(data["normalized_address"], str)
        assert isinstance(data["is_well_formed"], bool)
        assert isinstance(data["validation"], dict)
        assert isinstance(data["validation"]["present_components"], list)
        assert isinstance(data["validation"]["missing_components"], list)
        assert isinstance(data["validation"]["malformed_components"], list)
        assert isinstance(data["suggestions"], list)

        # Suggestion structure
        suggestion = data["suggestions"][0]
        assert isinstance(suggestion["address"], str)
        assert isinstance(suggestion["latitude"], float)
        assert isinstance(suggestion["longitude"], float)

    @pytest.mark.asyncio
    async def test_422_response_on_empty_address(self, client) -> None:
        """422 response on empty address."""
        resp = await client.get("/api/v1/geocoding/verify?address=")
        assert resp.status_code == 422
