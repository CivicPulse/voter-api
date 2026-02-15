"""Contract tests for publish status and discovery endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1 import boundaries as boundaries_module
from voter_api.api.v1.boundaries import boundaries_router
from voter_api.api.v1.datasets import datasets_router
from voter_api.core.dependencies import get_async_session, get_current_user
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
        }
    return ManifestData(
        version="1",
        published_at=datetime(2026, 2, 12, 15, 30, 0, tzinfo=UTC),
        publisher_version="0.1.0",
        datasets=datasets,
    )


@pytest.fixture(autouse=True)
def _reset_manifest_cache():
    """Reset manifest cache between tests."""
    boundaries_module._manifest_cache = None
    yield
    boundaries_module._manifest_cache = None


@pytest.fixture
def mock_settings_r2_enabled():
    """Mock settings with R2 enabled."""
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
    """Mock settings with R2 disabled."""
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

    mock_user = MagicMock()
    mock_user.role = "admin"
    app.dependency_overrides[get_current_user] = lambda: mock_user
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False)


class TestPublishStatusContract:
    """Contract tests for GET /api/v1/boundaries/publish/status."""

    @pytest.mark.asyncio
    async def test_response_matches_schema_when_configured(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Response matches PublishStatusResponse schema."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/boundaries/publish/status")

        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert isinstance(data["configured"], bool)
        assert "manifest_loaded" in data
        assert "datasets" in data
        assert isinstance(data["datasets"], list)

    @pytest.mark.asyncio
    async def test_configured_false_when_r2_disabled(self, client: AsyncClient, mock_settings_r2_disabled) -> None:
        """configured=false when R2 disabled."""
        with patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_disabled):
            resp = await client.get("/api/v1/boundaries/publish/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    @pytest.mark.asyncio
    async def test_datasets_list_matches_manifest(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """datasets list matches manifest entries when configured."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/boundaries/publish/status")

        data = resp.json()
        assert len(data["datasets"]) == 1
        ds = data["datasets"][0]
        assert ds["name"] == "congressional"
        assert ds["record_count"] == 14
        assert ds["file_size_bytes"] == 2340500
        assert "published_at" in ds


class TestDiscoveryContract:
    """Contract tests for GET /api/v1/datasets."""

    @pytest.mark.asyncio
    async def test_response_matches_schema(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Response matches DatasetDiscoveryResponse schema."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
        data = resp.json()
        assert "base_url" in data
        assert "datasets" in data
        assert isinstance(data["datasets"], list)

    @pytest.mark.asyncio
    async def test_base_url_matches_setting(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """base_url matches R2_PUBLIC_URL setting."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/datasets")

        data = resp.json()
        assert data["base_url"] == "https://geo.example.com"

    @pytest.mark.asyncio
    async def test_datasets_reflect_manifest(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """datasets list reflects manifest entries."""
        cache = ManifestCache(ttl_seconds=300)
        cache.set(_make_manifest_data())
        boundaries_module._manifest_cache = cache

        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled):
            resp = await client.get("/api/v1/datasets")

        data = resp.json()
        assert len(data["datasets"]) == 1
        ds = data["datasets"][0]
        assert ds["name"] == "congressional"
        assert ds["record_count"] == 14
        assert ds["boundary_type"] == "congressional"

    @pytest.mark.asyncio
    async def test_empty_datasets_when_no_manifest(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Empty datasets list when no manifest loaded."""
        with (
            patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled),
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
        ):
            resp = await client.get("/api/v1/datasets")

        data = resp.json()
        assert data["datasets"] == []
        assert data["base_url"] == "https://geo.example.com"

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient, mock_settings_r2_enabled) -> None:
        """Endpoint requires no authentication."""
        with (
            patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_enabled),
            patch("voter_api.api.v1.boundaries.get_settings", return_value=mock_settings_r2_enabled),
        ):
            resp = await client.get("/api/v1/datasets")

        # No 401 or 403 — endpoint is public
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_r2_not_configured_returns_null_base_url(
        self, client: AsyncClient, mock_settings_r2_disabled
    ) -> None:
        """Returns base_url=null and empty datasets when R2 not configured."""
        with patch("voter_api.api.v1.datasets.get_settings", return_value=mock_settings_r2_disabled):
            resp = await client.get("/api/v1/datasets")

        assert resp.status_code == 200
        data = resp.json()
        assert data["base_url"] is None
        assert data["datasets"] == []
