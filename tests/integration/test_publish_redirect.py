"""Integration tests for API redirect to static files on R2 and dataset discovery."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1 import boundaries as boundaries_module
from voter_api.api.v1.boundaries import boundaries_router
from voter_api.api.v1.datasets import datasets_router
from voter_api.core.dependencies import get_async_session
from voter_api.lib.publisher.manifest import ManifestCache
from voter_api.lib.publisher.types import DatasetEntry, ManifestData


def _make_manifest_data(datasets: dict[str, DatasetEntry] | None = None) -> ManifestData:
    """Create a test ManifestData."""
    if datasets is None:
        datasets = {
            "congressional": DatasetEntry(
                name="congressional",
                key="boundaries/congressional.geojson",
                public_url="https://geo.example.com/boundaries/congressional.geojson",
                content_type="application/geo+json",
                record_count=14,
                file_size_bytes=2340500,
                boundary_type="congressional",
                filters={"boundary_type": "congressional"},
                published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
            ),
            "all-boundaries": DatasetEntry(
                name="all-boundaries",
                key="boundaries/all-boundaries.geojson",
                public_url="https://geo.example.com/boundaries/all-boundaries.geojson",
                content_type="application/geo+json",
                record_count=100,
                file_size_bytes=5000000,
                boundary_type=None,
                filters={},
                published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
            ),
        }
    return ManifestData(
        version="1",
        published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
        publisher_version="0.1.0",
        datasets=datasets,
    )


@pytest.fixture(autouse=True)
def _reset_manifest_cache():
    """Reset the module-level manifest cache between tests."""
    boundaries_module._manifest_cache = None
    yield
    boundaries_module._manifest_cache = None


@pytest.fixture
def mock_settings_r2_enabled():
    """Create mock settings with R2 enabled."""
    settings = MagicMock()
    settings.r2_enabled = True
    settings.r2_account_id = "test-account"
    settings.r2_access_key_id = "test-key"
    settings.r2_secret_access_key = "test-secret"
    settings.r2_bucket = "test-bucket"
    settings.r2_public_url = "https://geo.example.com"
    settings.r2_prefix = ""
    settings.r2_manifest_ttl = 300
    settings.api_v1_prefix = "/api/v1"
    return settings


@pytest.fixture
def mock_settings_r2_disabled():
    """Create mock settings with R2 disabled."""
    settings = MagicMock()
    settings.r2_enabled = False
    settings.r2_manifest_ttl = 300
    settings.api_v1_prefix = "/api/v1"
    return settings


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with boundaries and datasets routers."""
    app = FastAPI()
    app.include_router(boundaries_router, prefix="/api/v1")
    app.include_router(datasets_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)


class TestRedirectWithManifest:
    """Tests for 302 redirect when manifest has matching dataset."""

    @pytest.mark.asyncio
    async def test_returns_302_with_location_for_all_boundaries(
        self, client: AsyncClient, mock_settings_r2_enabled
    ) -> None:
        """Endpoint returns 302 with Location header when manifest has all-boundaries."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://geo.example.com/boundaries/all-boundaries.geojson"

    @pytest.mark.asyncio
    async def test_returns_302_for_boundary_type_filter(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Endpoint returns 302 for boundary_type filter matching published dataset."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/boundaries/geojson?boundary_type=congressional")

        assert resp.status_code == 302
        assert resp.headers["location"] == "https://geo.example.com/boundaries/congressional.geojson"


class TestFallbackToDB:
    """Tests for 200 fallback to database when redirect is not applicable."""

    @pytest.mark.asyncio
    async def test_returns_200_when_r2_disabled(self, client: AsyncClient, mock_settings_r2_disabled) -> None:
        """Endpoint returns 200 GeoJSON from database when R2 is not configured."""
        with (
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_disabled),
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"

    @pytest.mark.asyncio
    async def test_returns_200_for_county_filter(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Endpoint returns 200 fallback when county filter is used."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with (
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            resp = await client.get("/api/v1/boundaries/geojson?county=Fulton")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_returns_200_when_manifest_empty(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Endpoint returns 200 when manifest has no datasets."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data(datasets={}))
        boundaries_module._manifest_cache = cache

        with (
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([], 0),
            ),
        ):
            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.status_code == 200


class TestDiscoveryEndpointIntegration:
    """Integration tests for GET /api/v1/datasets discovery endpoint."""

    @pytest.mark.asyncio
    async def test_returns_datasets_from_cached_manifest(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Returns 200 with base_url and datasets from cached manifest."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] == "https://geo.example.com"
        assert len(data["datasets"]) == 2
        names = {ds["name"] for ds in data["datasets"]}
        assert "congressional" in names
        assert "all-boundaries" in names

    @pytest.mark.asyncio
    async def test_returns_null_base_url_when_r2_disabled(self, client: AsyncClient, mock_settings_r2_disabled) -> None:
        """Returns base_url=null and empty datasets when R2 not configured."""
        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_disabled):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] is None
        assert data["datasets"] == []

    @pytest.mark.asyncio
    async def test_returns_empty_datasets_when_no_manifest(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Returns base_url with empty datasets when R2 configured but no manifest."""
        with (
            patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled),
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
        ):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] == "https://geo.example.com"
        assert data["datasets"] == []

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Endpoint requires no authentication — no Authorization header needed."""
        with (
            patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled),
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
        ):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
