"""Integration tests for geocoding API endpoints."""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from voter_api.api.v1.geocoding import geocoding_router
from voter_api.lib.geocoder.base import GeocodingProviderError
from voter_api.models.geocoding_job import GeocodingJob
from voter_api.schemas.geocoding import AddressGeocodeResponse, CacheProviderStats, GeocodeMetadata

from .conftest import make_test_app


def _make_geocoding_job(
    *,
    job_id: uuid.UUID | None = None,
    provider: str = "census",
    status: str = "pending",
    county: str | None = None,
    total_records: int | None = None,
    processed: int | None = None,
    succeeded: int | None = None,
    failed: int | None = None,
) -> GeocodingJob:
    """Build a GeocodingJob ORM object for use in mocks."""
    return GeocodingJob(
        id=job_id or uuid.uuid4(),
        provider=provider,
        status=status,
        force_regeocode=False,
        county=county,
        total_records=total_records,
        processed=processed,
        succeeded=succeeded,
        failed=failed,
        created_at=datetime.now(UTC),
    )


def _make_geocode_response(*, cached: bool = False, provider: str = "census") -> AddressGeocodeResponse:
    """Build an AddressGeocodeResponse for use in mocks."""
    return AddressGeocodeResponse(
        formatted_address="100 PEACHTREE ST NW, ATLANTA, GA 30303",
        latitude=33.7589985,
        longitude=-84.3879824,
        confidence=1.0,
        metadata=GeocodeMetadata(cached=cached, provider=provider),
    )


@contextmanager
def _patch_batch_create(mock_job: GeocodingJob):
    """Patch create_geocoding_job and task_runner for batch endpoint tests."""
    with (
        patch(
            "voter_api.api.v1.geocoding.create_geocoding_job",
            new_callable=AsyncMock,
            return_value=mock_job,
        ),
        patch("voter_api.api.v1.geocoding.task_runner") as mock_runner,
    ):
        mock_runner.submit_task = MagicMock()
        yield mock_runner


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Create a minimal FastAPI app with geocoding router (no auth override)."""
    return make_test_app(geocoding_router, mock_session)


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    return make_test_app(geocoding_router, mock_session, user=mock_admin_user)


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """FastAPI app with viewer auth."""
    return make_test_app(geocoding_router, mock_session, user=mock_viewer_user)


class TestGeocodeEndpoint:
    """Tests for GET /api/v1/geocoding/geocode."""

    async def test_valid_address_returns_200(self, client) -> None:
        """Valid address returns 200 with required fields."""
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=_make_geocode_response(),
        ):
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
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=_make_geocode_response(),
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Main+St")
        assert resp.status_code == 200


class TestGeocodeCacheBehavior:
    """Tests for US2: cached results returned with metadata.cached flag."""

    @pytest.mark.parametrize("cached", [True, False], ids=["cached", "uncached"])
    async def test_cache_flag_matches_response(self, client, cached: bool) -> None:
        """Response metadata.cached reflects whether the result was served from cache."""
        with patch(
            "voter_api.api.v1.geocoding.geocode_single_address",
            new_callable=AsyncMock,
            return_value=_make_geocode_response(cached=cached),
        ):
            resp = await client.get("/api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303")

        assert resp.status_code == 200
        assert resp.json()["metadata"]["cached"] is cached


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
        with _patch_batch_create(_make_geocoding_job()):
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census"})

        assert resp.status_code == 202
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert data["provider"] == "census"

    async def test_accepts_fallback_true(self, admin_client) -> None:
        """Batch endpoint accepts fallback=True and creates job."""
        with _patch_batch_create(_make_geocoding_job()):
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census", "fallback": True})

        assert resp.status_code == 202

    async def test_accepts_county_filter(self, admin_client) -> None:
        """Batch endpoint accepts optional county filter."""
        with _patch_batch_create(_make_geocoding_job(county="FULTON")):
            resp = await admin_client.post("/api/v1/geocoding/batch", json={"provider": "census", "county": "FULTON"})

        assert resp.status_code == 202
        assert resp.json()["county"] == "FULTON"

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
        resp = await client.get(f"/api/v1/geocoding/status/{uuid.uuid4()}")
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
        job_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
        mock_job = _make_geocoding_job(
            job_id=job_id, status="completed", total_records=10, processed=10, succeeded=8, failed=2
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
        job_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
        with patch(
            "voter_api.api.v1.geocoding.get_geocoding_job",
            new_callable=AsyncMock,
            return_value=_make_geocoding_job(job_id=job_id),
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
