"""Integration tests for geocoding API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.lib.geocoder.base import GeocodingProviderError, GeocodingResult


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    return AsyncMock()


@pytest.fixture
def mock_admin_user() -> MagicMock:
    """Mock admin user for dependency override."""
    user = MagicMock()
    user.role = "admin"
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user.username = "admin"
    user.is_active = True
    return user


@pytest.fixture
def mock_viewer_user() -> MagicMock:
    """Mock viewer user for dependency override."""
    user = MagicMock()
    user.role = "viewer"
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    user.username = "viewer"
    user.is_active = True
    return user


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Create a minimal FastAPI app with geocoding router (no auth override)."""
    app = FastAPI()
    app.include_router(geocoding_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    app = FastAPI()
    app.include_router(geocoding_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """FastAPI app with viewer auth."""
    app = FastAPI()
    app.include_router(geocoding_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client (no auth)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with admin auth."""
    async with AsyncClient(
        transport=ASGITransport(app=admin_app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with viewer auth."""
    async with AsyncClient(
        transport=ASGITransport(app=viewer_app),
        base_url="http://test",  # NOSONAR — in-memory ASGI transport, no real HTTP
        follow_redirects=False,
    ) as c:
        yield c


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

    async def test_empty_address_returns_422(self, client) -> None:
        """Empty address returns 422 validation error."""
        resp = await client.get("/api/v1/geocoding/geocode?address=")
        assert resp.status_code == 422

    async def test_whitespace_only_returns_422(self, client) -> None:
        """Whitespace-only address returns 422."""
        resp = await client.get("/api/v1/geocoding/geocode?address=%20%20%20")
        assert resp.status_code == 422

    async def test_address_too_long_returns_422(self, client) -> None:
        """Address exceeding 500 chars returns 422."""
        long_addr = "A" * 501
        resp = await client.get(f"/api/v1/geocoding/geocode?address={long_addr}")
        assert resp.status_code == 422

    async def test_anonymous_access_allowed(self, client) -> None:
        """Anonymous (unauthenticated) requests are allowed — endpoint is public."""
        from voter_api.schemas.geocoding import AddressGeocodeResponse, GeocodeMetadata

        mock_response = AddressGeocodeResponse(
            formatted_address="100 MAIN ST, ATLANTA, GA 30303",
            latitude=33.749,
            longitude=-84.388,
            confidence=0.95,
            metadata=GeocodeMetadata(cached=False, provider="census"),
        )
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Main+St")
        assert resp.status_code == 200


class TestGeocodeCacheBehavior:
    """Tests for US2: cached results returned with metadata.cached=true."""

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


class TestBatchGeocodingEndpoint:
    """Tests for POST /api/v1/geocoding/batch (admin-only)."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.post("/api/v1/geocoding/batch", json={"provider": "census"})
        assert resp.status_code == 401

    async def test_admin_creates_job_returns_202(self, admin_client) -> None:
        """Admin request creates a geocoding job and returns 202 with job fields."""
        from datetime import UTC, datetime

        from voter_api.models.geocoding_job import GeocodingJob

        mock_job = GeocodingJob(
            id=uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
            provider="census",
            status="pending",
            force_regeocode=False,
            created_at=datetime.now(UTC),
        )
        with (
            patch(
                "voter_api.api.v1.geocoding.create_geocoding_job",
                new_callable=AsyncMock,
                return_value=mock_job,
            ),
            patch("voter_api.api.v1.geocoding.task_runner") as mock_runner,
        ):
            mock_runner.submit_task = MagicMock()
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census"})

        assert resp.status_code == 202
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["provider"] == "census"

    async def test_accepts_fallback_true(self, admin_client) -> None:
        """Batch endpoint accepts fallback=True and creates job."""
        from datetime import UTC, datetime

        from voter_api.models.geocoding_job import GeocodingJob

        mock_job = GeocodingJob(
            id=uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"),
            provider="census",
            status="pending",
            force_regeocode=False,
            created_at=datetime.now(UTC),
        )
        with (
            patch(
                "voter_api.api.v1.geocoding.create_geocoding_job",
                new_callable=AsyncMock,
                return_value=mock_job,
            ),
            patch("voter_api.api.v1.geocoding.task_runner") as mock_runner,
        ):
            mock_runner.submit_task = MagicMock()
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census", "fallback": True})

        assert resp.status_code == 202

    async def test_accepts_county_filter(self, admin_client) -> None:
        """Batch endpoint accepts optional county filter."""
        from datetime import UTC, datetime

        from voter_api.models.geocoding_job import GeocodingJob

        mock_job = GeocodingJob(
            id=uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003"),
            provider="census",
            county="FULTON",
            status="pending",
            force_regeocode=False,
            created_at=datetime.now(UTC),
        )
        with (
            patch(
                "voter_api.api.v1.geocoding.create_geocoding_job",
                new_callable=AsyncMock,
                return_value=mock_job,
            ),
            patch("voter_api.api.v1.geocoding.task_runner") as mock_runner,
        ):
            mock_runner.submit_task = MagicMock()
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census", "county": "FULTON"})

        assert resp.status_code == 202
        data = resp.json()
        assert data["county"] == "FULTON"

    async def test_viewer_cannot_create_batch_returns_403(self, viewer_client) -> None:
        """Viewer role cannot create batch job (admin-only endpoint returns 403)."""
        resp = await viewer_client.post("/api/v1/geocoding/batch", json={"provider": "census"})
        assert resp.status_code == 403

    async def test_invalid_provider_returns_422(self, admin_client) -> None:
        """Invalid provider value returns 422 (schema validation)."""
        resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "not-a-real-provider"})
        assert resp.status_code == 422


class TestGeocodingJobStatus:
    """Tests for GET /api/v1/geocoding/status/{job_id} (any authenticated user)."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        job_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/geocoding/status/{job_id}")
        assert resp.status_code == 401

    async def test_unknown_job_returns_404(self, admin_client) -> None:
        """Unknown job ID returns 404."""
        with patch(
            "voter_api.api.v1.geocoding.get_geocoding_job",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/geocoding/status/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_returns_job_fields(self, admin_client) -> None:
        """Returns 200 with geocoding job fields for authenticated user."""
        from datetime import UTC, datetime

        from voter_api.models.geocoding_job import GeocodingJob

        job_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
        mock_job = GeocodingJob(
            id=job_id,
            provider="census",
            status="completed",
            force_regeocode=False,
            total_records=10,
            processed=10,
            succeeded=8,
            failed=2,
            created_at=datetime.now(UTC),
        )
        with patch(
            "voter_api.api.v1.geocoding.get_geocoding_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ):
            resp = await admin_client.get(f"/api/v1/geocoding/status/{job_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(job_id)
        assert data["status"] == "completed"
        assert data["provider"] == "census"
        assert data["total_records"] == 10
        assert data["succeeded"] == 8
        assert data["failed"] == 2

    async def test_viewer_can_access(self, viewer_client) -> None:
        """Viewer role can access job status (requires any auth, not admin-only)."""
        from datetime import UTC, datetime

        from voter_api.models.geocoding_job import GeocodingJob

        job_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
        mock_job = GeocodingJob(
            id=job_id,
            provider="census",
            status="pending",
            force_regeocode=False,
            created_at=datetime.now(UTC),
        )
        with patch(
            "voter_api.api.v1.geocoding.get_geocoding_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ):
            resp = await viewer_client.get(f"/api/v1/geocoding/status/{job_id}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"


class TestCacheStatsEndpoint:
    """Tests for GET /api/v1/geocoding/cache/stats (any authenticated user)."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.get("/api/v1/geocoding/cache/stats")
        assert resp.status_code == 401

    async def test_returns_provider_stats(self, admin_client) -> None:
        """Returns 200 with per-provider cache statistics."""
        from datetime import UTC, datetime

        from voter_api.schemas.geocoding import CacheProviderStats

        mock_stats = [
            CacheProviderStats(
                provider="census",
                cached_count=42,
                oldest_entry=datetime(2024, 1, 1, tzinfo=UTC),
                newest_entry=datetime.now(UTC),
            ),
        ]
        with patch(
            "voter_api.api.v1.geocoding.get_cache_stats",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ):
            resp = await admin_client.get("/api/v1/geocoding/cache/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert len(data["providers"]) == 1
        assert data["providers"][0]["provider"] == "census"
        assert data["providers"][0]["cached_count"] == 42

    async def test_empty_cache_returns_empty_list(self, admin_client) -> None:
        """Returns 200 with empty list when cache is empty."""
        with patch(
            "voter_api.api.v1.geocoding.get_cache_stats",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await admin_client.get("/api/v1/geocoding/cache/stats")

        assert resp.status_code == 200
        assert resp.json()["providers"] == []

    async def test_viewer_can_access(self, viewer_client) -> None:
        """Viewer role can access cache stats (requires any auth, not admin-only)."""
        with patch(
            "voter_api.api.v1.geocoding.get_cache_stats",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await viewer_client.get("/api/v1/geocoding/cache/stats")

        assert resp.status_code == 200
