"""Integration tests for GET /geocoding/geocode endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.lib.geocoder.base import GeocodingProviderError, GeocodingResult


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


@pytest.fixture
def mock_geocode_result():
    """A successful geocode result in Georgia."""
    return GeocodingResult(
        latitude=33.7589985,
        longitude=-84.3879824,
        confidence_score=1.0,
        raw_response={"result": {"addressMatches": [{"matchedAddress": "100 PEACHTREE ST NW, ATLANTA, GA 30303"}]}},
        matched_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
    )


class TestGeocodeEndpoint:
    """Tests for GET /api/v1/geocoding/geocode."""

    @pytest.mark.asyncio
    async def test_valid_address_returns_200(self, client, mock_geocode_result) -> None:
        """Valid address returns 200 with required fields."""
        with (
            patch("voter_api.api.v1.geocoding.geocode_single_address", new_callable=AsyncMock) as mock_geocode,
        ):
            from voter_api.schemas.geocoding import AddressGeocodeResponse, GeocodeMetadata

            mock_geocode.return_value = AddressGeocodeResponse(
                formatted_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
                latitude=33.7589985,
                longitude=-84.3879824,
                confidence=1.0,
                metadata=GeocodeMetadata(cached=False, provider="census"),
            )

            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()
        assert "formatted_address" in data
        assert "latitude" in data
        assert "longitude" in data
        assert "confidence" in data
        assert "metadata" in data
        assert "cached" in data["metadata"]
        assert "provider" in data["metadata"]

    @pytest.mark.asyncio
    async def test_empty_address_returns_422(self, client) -> None:
        """Empty address returns 422 validation error."""
        resp = await client.get("/api/v1/geocoding/geocode?address=")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_422(self, client) -> None:
        """Whitespace-only address returns 422."""
        resp = await client.get("/api/v1/geocoding/geocode?address=%20%20%20")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_address_too_long_returns_422(self, client) -> None:
        """Address exceeding 500 chars returns 422."""
        long_addr = "A" * 501
        resp = await client.get(f"/api/v1/geocoding/geocode?address={long_addr}")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self) -> None:
        """Missing auth token returns 401."""
        app = FastAPI()
        app.include_router(geocoding_router, prefix="/api/v1")
        # Override session but NOT auth — should fail with 401
        app.dependency_overrides[get_async_session] = lambda: AsyncMock()
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)
        resp = await client.get("/api/v1/geocoding/geocode?address=100+Main+St")
        assert resp.status_code == 401


class TestGeocodeCacheBehavior:
    """Tests for US2: cached results returned with metadata.cached=true."""

    @pytest.mark.asyncio
    async def test_cached_result_has_cached_true(self, client) -> None:
        """Cached result has metadata.cached=true."""
        from voter_api.schemas.geocoding import AddressGeocodeResponse, GeocodeMetadata

        cached_response = AddressGeocodeResponse(
            formatted_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
            latitude=33.7589985,
            longitude=-84.3879824,
            confidence=1.0,
            metadata=GeocodeMetadata(cached=True, provider="census"),
        )
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=cached_response,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["cached"] is True

    @pytest.mark.asyncio
    async def test_uncached_result_has_cached_false(self, client) -> None:
        """Fresh result has metadata.cached=false."""
        from voter_api.schemas.geocoding import AddressGeocodeResponse, GeocodeMetadata

        fresh_response = AddressGeocodeResponse(
            formatted_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
            latitude=33.7589985,
            longitude=-84.3879824,
            confidence=1.0,
            metadata=GeocodeMetadata(cached=False, provider="census"),
        )
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=fresh_response,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        data = resp.json()
        assert data["metadata"]["cached"] is False


class TestGeocodeErrorPaths:
    """Tests for US3: graceful geocoding failure handling."""

    @pytest.mark.asyncio
    async def test_unmatchable_address_returns_404(self, client) -> None:
        """Address that cannot be geocoded returns 404 with descriptive message."""
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=99999+Nonexistent+Rd,+Nowhere,+GA+00000")

        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data
        assert "could not be geocoded" in data["detail"]

    @pytest.mark.asyncio
    async def test_provider_timeout_returns_502(self, client) -> None:
        """Provider timeout returns 502 with retry suggestion."""
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            side_effect=GeocodingProviderError("census", "Geocoding request timed out"),
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 502
        data = resp.json()
        assert "detail" in data
        assert "temporarily unavailable" in data["detail"].lower() or "retry" in data["detail"].lower()
