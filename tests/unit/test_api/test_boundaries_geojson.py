"""Unit tests for public boundary endpoints (no authentication required)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.boundaries import boundaries_router
from voter_api.core.dependencies import get_async_session


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with the boundaries router and mocked DB session."""
    app = FastAPI()
    app.include_router(boundaries_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create an async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _make_mock_boundary(
    *,
    name: str = "Test County",
    boundary_type: str = "county",
    boundary_identifier: str = "001",
    source: str = "state",
    county: str | None = None,
) -> MagicMock:
    """Create a mock Boundary object with a WKB geometry."""
    boundary = MagicMock()
    boundary.id = uuid.uuid4()
    boundary.name = name
    boundary.boundary_type = boundary_type
    boundary.boundary_identifier = boundary_identifier
    boundary.source = source
    boundary.county = county
    boundary.effective_date = None
    boundary.created_at = datetime.now(tz=UTC)
    boundary.properties = {}
    boundary.geometry = MagicMock()
    return boundary


class TestGetBoundariesGeoJSON:
    """Tests for GET /api/v1/boundaries/geojson."""

    @pytest.mark.asyncio
    async def test_returns_feature_collection_structure(self, client: AsyncClient) -> None:
        """Endpoint returns a valid GeoJSON FeatureCollection."""
        mock_boundary = _make_mock_boundary()

        with (
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([mock_boundary], 1),
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            }

            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature
        assert feature["properties"]["name"] == "Test County"

    @pytest.mark.asyncio
    async def test_content_type_is_geo_json(self, client: AsyncClient) -> None:
        """Response Content-Type is application/geo+json."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.headers["content-type"] == "application/geo+json"

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_collection(self, client: AsyncClient) -> None:
        """Empty DB returns an empty FeatureCollection."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await client.get("/api/v1/boundaries/geojson")

        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient) -> None:
        """Endpoint does not require a JWT token."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await client.get("/api/v1/boundaries/geojson")

        # Should succeed without any Authorization header
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_filters_by_boundary_type(self, client: AsyncClient) -> None:
        """Query param boundary_type is forwarded to the service."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            await client.get("/api/v1/boundaries/geojson?boundary_type=county")

        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["boundary_type"] == "county"

    @pytest.mark.asyncio
    async def test_filters_by_county(self, client: AsyncClient) -> None:
        """Query param county is forwarded to the service."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            await client.get("/api/v1/boundaries/geojson?county=Fulton")

        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["county"] == "Fulton"

    @pytest.mark.asyncio
    async def test_filters_by_source(self, client: AsyncClient) -> None:
        """Query param source is forwarded to the service."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            await client.get("/api/v1/boundaries/geojson?source=state")

        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["source"] == "state"

    @pytest.mark.asyncio
    async def test_feature_properties_contain_expected_keys(self, client: AsyncClient) -> None:
        """Each feature's properties include name, boundary_type, boundary_identifier, source, and county."""
        mock_boundary = _make_mock_boundary(county="Fulton")

        with (
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([mock_boundary], 1),
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            }

            resp = await client.get("/api/v1/boundaries/geojson")

        props = resp.json()["features"][0]["properties"]
        assert set(props.keys()) == {"name", "boundary_type", "boundary_identifier", "source", "county"}
        assert props["county"] == "Fulton"

    @pytest.mark.asyncio
    async def test_feature_id_is_string(self, client: AsyncClient) -> None:
        """Feature id is a string representation of the boundary UUID."""
        mock_boundary = _make_mock_boundary()

        with (
            patch(
                "voter_api.api.v1.boundaries.list_boundaries",
                new_callable=AsyncMock,
                return_value=([mock_boundary], 1),
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get("/api/v1/boundaries/geojson")

        feature = resp.json()["features"][0]
        assert isinstance(feature["id"], str)
        # Should be a valid UUID string
        uuid.UUID(feature["id"])


class TestListAllBoundariesNoAuth:
    """Tests for GET /api/v1/boundaries (no auth required)."""

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient) -> None:
        """Endpoint does not require a JWT token."""
        with patch(
            "voter_api.api.v1.boundaries.list_boundaries",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await client.get("/api/v1/boundaries")

        assert resp.status_code == 200


class TestContainingPointNoAuth:
    """Tests for GET /api/v1/boundaries/containing-point (no auth required)."""

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient) -> None:
        """Endpoint does not require a JWT token."""
        with patch(
            "voter_api.api.v1.boundaries.find_containing_boundaries",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/api/v1/boundaries/containing-point?latitude=33.7&longitude=-84.4")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_filters_by_county(self, client: AsyncClient) -> None:
        """Query param county is forwarded to find_containing_boundaries."""
        with patch(
            "voter_api.api.v1.boundaries.find_containing_boundaries",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find:
            await client.get("/api/v1/boundaries/containing-point?latitude=33.7&longitude=-84.4&county=Bibb")

        assert mock_find.call_args.kwargs.get("county") == "Bibb"


class TestGetBoundaryDetailNoAuth:
    """Tests for GET /api/v1/boundaries/{boundary_id} (no auth required)."""

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client: AsyncClient) -> None:
        """Endpoint does not require a JWT token."""
        mock_boundary = _make_mock_boundary()

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {
                "type": "MultiPolygon",
                "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
            }

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
