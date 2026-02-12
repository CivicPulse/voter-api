"""Tests for county and precinct metadata in boundary detail endpoint."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
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
    boundary_type: str = "county",
    boundary_identifier: str = "13121",
) -> MagicMock:
    """Create a mock Boundary object."""
    boundary = MagicMock()
    boundary.id = uuid.uuid4()
    boundary.name = "Fulton"
    boundary.boundary_type = boundary_type
    boundary.boundary_identifier = boundary_identifier
    boundary.source = "state"
    boundary.county = None
    boundary.effective_date = None
    boundary.created_at = datetime.now(tz=UTC)
    boundary.properties = {}
    boundary.geometry = MagicMock()
    return boundary


def _make_mock_metadata() -> MagicMock:
    """Create a mock CountyMetadata object."""
    meta = MagicMock()
    meta.geoid = "13121"
    meta.fips_state = "13"
    meta.fips_county = "121"
    meta.gnis_code = "01694833"
    meta.geoid_fq = "0500000US13121"
    meta.name = "Fulton"
    meta.name_lsad = "Fulton County"
    meta.lsad_code = "06"
    meta.class_fp = "H1"
    meta.mtfcc = "G4020"
    meta.csa_code = "122"
    meta.cbsa_code = "12060"
    meta.metdiv_code = "12054"
    meta.functional_status = "A"
    meta.land_area_m2 = 1364558845
    meta.water_area_m2 = 20564942
    meta.internal_point_lat = "+33.7900338"
    meta.internal_point_lon = "-084.4681816"
    return meta


class TestBoundaryDetailCountyMetadata:
    """Tests for county_metadata field in boundary detail response."""

    @pytest.mark.asyncio
    async def test_county_boundary_includes_metadata(self, client: AsyncClient) -> None:
        """County boundary detail includes county_metadata when metadata exists."""
        mock_boundary = _make_mock_boundary(boundary_type="county", boundary_identifier="13121")
        mock_metadata = _make_mock_metadata()

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_county_metadata_by_geoid",
                new_callable=AsyncMock,
                return_value=mock_metadata,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["county_metadata"] is not None
        assert data["county_metadata"]["geoid"] == "13121"
        assert data["county_metadata"]["name"] == "Fulton"
        assert data["county_metadata"]["land_area_m2"] == 1364558845
        assert data["county_metadata"]["land_area_km2"] == pytest.approx(1364.56)
        assert data["county_metadata"]["water_area_km2"] == pytest.approx(20.56)

    @pytest.mark.asyncio
    async def test_non_county_boundary_has_null_metadata(self, client: AsyncClient) -> None:
        """Non-county boundary detail has county_metadata as null."""
        mock_boundary = _make_mock_boundary(boundary_type="congressional", boundary_identifier="1401")

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
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["county_metadata"] is None

    @pytest.mark.asyncio
    async def test_county_boundary_without_metadata_has_null(self, client: AsyncClient) -> None:
        """County boundary with no matching metadata record has county_metadata as null."""
        mock_boundary = _make_mock_boundary(boundary_type="county", boundary_identifier="99999")

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_county_metadata_by_geoid",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["county_metadata"] is None

    @pytest.mark.asyncio
    async def test_metadata_lookup_uses_boundary_identifier(self, client: AsyncClient) -> None:
        """Metadata lookup uses boundary_identifier as the GEOID."""
        mock_boundary = _make_mock_boundary(boundary_type="county", boundary_identifier="13067")

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_county_metadata_by_geoid",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get_meta,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        # Verify it was called with the boundary_identifier as GEOID
        assert mock_get_meta.await_count == 1
        call_args, _ = mock_get_meta.await_args_list[0]
        assert call_args[1] == "13067"


def _make_mock_precinct_metadata() -> MagicMock:
    """Create a mock PrecinctMetadata object."""
    meta = MagicMock()
    meta.sos_district_id = "121001"
    meta.sos_id = "13121001"
    meta.fips = "13121"
    meta.fips_county = "121"
    meta.county_name = "Fulton"
    meta.county_number = "059"
    meta.precinct_id = "12A"
    meta.precinct_name = "Sandy Springs North"
    meta.area = Decimal("2.456789")
    return meta


class TestBoundaryDetailPrecinctMetadata:
    """Tests for precinct_metadata field in boundary detail response."""

    @pytest.mark.asyncio
    async def test_precinct_boundary_includes_metadata(self, client: AsyncClient) -> None:
        """County precinct boundary detail includes precinct_metadata when metadata exists."""
        mock_boundary = _make_mock_boundary(
            boundary_type="county_precinct",
            boundary_identifier="121-12A",
        )
        mock_metadata = _make_mock_precinct_metadata()

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_precinct_metadata_by_boundary",
                new_callable=AsyncMock,
                return_value=mock_metadata,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["precinct_metadata"] is not None
        assert data["precinct_metadata"]["sos_district_id"] == "121001"
        assert data["precinct_metadata"]["precinct_name"] == "Sandy Springs North"
        assert data["precinct_metadata"]["precinct_id"] == "12A"
        assert data["precinct_metadata"]["fips"] == "13121"

    @pytest.mark.asyncio
    async def test_non_precinct_boundary_has_null_precinct_metadata(self, client: AsyncClient) -> None:
        """Non-precinct boundary detail has precinct_metadata as null."""
        mock_boundary = _make_mock_boundary(boundary_type="county", boundary_identifier="13121")

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_county_metadata_by_geoid",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["precinct_metadata"] is None

    @pytest.mark.asyncio
    async def test_precinct_boundary_without_metadata_has_null(self, client: AsyncClient) -> None:
        """County precinct boundary with no matching metadata record has precinct_metadata as null."""
        mock_boundary = _make_mock_boundary(
            boundary_type="county_precinct",
            boundary_identifier="121-99Z",
        )

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_precinct_metadata_by_boundary",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["precinct_metadata"] is None
