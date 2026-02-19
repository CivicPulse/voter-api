"""Tests for voter_stats enrichment in boundary detail endpoint."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.boundaries import boundaries_router
from voter_api.core.dependencies import get_async_session
from voter_api.schemas.voter_stats import VoterRegistrationStatsResponse, VoterStatusCount


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
    boundary_type: str = "congressional",
    boundary_identifier: str = "5",
    county: str | None = None,
) -> MagicMock:
    """Create a mock Boundary object."""
    boundary = MagicMock()
    boundary.id = uuid.uuid4()
    boundary.name = f"Test {boundary_type} {boundary_identifier}"
    boundary.boundary_type = boundary_type
    boundary.boundary_identifier = boundary_identifier
    boundary.source = "state"
    boundary.county = county
    boundary.effective_date = None
    boundary.created_at = datetime.now(tz=UTC)
    boundary.properties = {}
    boundary.geometry = MagicMock()
    return boundary


def _make_mock_voter_stats(
    total: int = 5300,
    by_status: list[tuple[str, int]] | None = None,
) -> VoterRegistrationStatsResponse:
    """Create a VoterRegistrationStatsResponse."""
    if by_status is None:
        by_status = [("A", 5000), ("I", 300)]
    return VoterRegistrationStatsResponse(
        total=total,
        by_status=[VoterStatusCount(status=s, count=c) for s, c in by_status],
    )


def _make_mock_county_metadata(name: str = "Fulton") -> MagicMock:
    """Create a mock CountyMetadata with all required fields for Pydantic validation."""
    meta = MagicMock()
    meta.geoid = "13121"
    meta.fips_state = "13"
    meta.fips_county = "121"
    meta.gnis_code = "01694833"
    meta.geoid_fq = "0500000US13121"
    meta.name = name
    meta.name_lsad = f"{name} County"
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


class TestBoundaryDetailVoterStats:
    """Tests for voter_stats field in boundary detail response."""

    @pytest.mark.asyncio
    async def test_congressional_boundary_includes_voter_stats(self, client: AsyncClient) -> None:
        """Congressional boundary detail includes voter_stats when voters exist."""
        mock_boundary = _make_mock_boundary(boundary_type="congressional", boundary_identifier="5")
        mock_stats = _make_mock_voter_stats(total=5300)

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["voter_stats"] is not None
        assert data["voter_stats"]["total"] == 5300
        assert len(data["voter_stats"]["by_status"]) == 2
        assert data["voter_stats"]["by_status"][0]["status"] == "A"
        assert data["voter_stats"]["by_status"][0]["count"] == 5000

    @pytest.mark.asyncio
    async def test_unmapped_boundary_type_has_null_voter_stats(self, client: AsyncClient) -> None:
        """Boundary types without voter field mapping have voter_stats as null."""
        mock_boundary = _make_mock_boundary(boundary_type="psc", boundary_identifier="1")

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["voter_stats"] is None

    @pytest.mark.asyncio
    async def test_county_boundary_resolves_name_from_metadata(self, client: AsyncClient) -> None:
        """County boundary resolves county name from county_metadata for voter stats."""
        mock_boundary = _make_mock_boundary(boundary_type="county", boundary_identifier="13121")
        mock_metadata = _make_mock_county_metadata("Fulton")
        mock_stats = _make_mock_voter_stats(total=50000)

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
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ) as mock_get_stats,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["voter_stats"] is not None
        assert data["voter_stats"]["total"] == 50000

        # Verify county_name_override was passed
        call_kwargs = mock_get_stats.await_args[1]
        assert call_kwargs["county_name_override"] == "Fulton"

    @pytest.mark.asyncio
    async def test_county_boundary_without_metadata_has_null_voter_stats(self, client: AsyncClient) -> None:
        """County boundary with no county_metadata cannot resolve name, voter_stats is null."""
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
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_get_stats,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["voter_stats"] is None

        # Verify county_name_override was None (no metadata to resolve from)
        call_kwargs = mock_get_stats.await_args[1]
        assert call_kwargs["county_name_override"] is None

    @pytest.mark.asyncio
    async def test_county_scoped_boundary_passes_county(self, client: AsyncClient) -> None:
        """County-scoped boundaries pass boundary.county to voter stats service."""
        mock_boundary = _make_mock_boundary(
            boundary_type="county_commission",
            boundary_identifier="3",
            county="Bibb",
        )
        mock_stats = _make_mock_voter_stats(total=1200, by_status=[("A", 1200)])

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ) as mock_get_stats,
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["voter_stats"]["total"] == 1200

        # Verify county was passed through
        call_kwargs = mock_get_stats.await_args[1]
        assert call_kwargs["county"] == "Bibb"

    @pytest.mark.asyncio
    async def test_boundary_with_zero_voters(self, client: AsyncClient) -> None:
        """Boundary with no matching voters returns total=0 and empty by_status."""
        mock_boundary = _make_mock_boundary(boundary_type="state_senate", boundary_identifier="56")
        mock_stats = VoterRegistrationStatsResponse(total=0, by_status=[])

        with (
            patch(
                "voter_api.api.v1.boundaries.get_boundary",
                new_callable=AsyncMock,
                return_value=mock_boundary,
            ),
            patch("voter_api.api.v1.boundaries.to_shape") as mock_to_shape,
            patch("voter_api.api.v1.boundaries.mapping") as mock_mapping,
            patch(
                "voter_api.api.v1.boundaries.get_voter_stats_for_boundary",
                new_callable=AsyncMock,
                return_value=mock_stats,
            ),
        ):
            mock_to_shape.return_value = MagicMock()
            mock_mapping.return_value = {"type": "MultiPolygon", "coordinates": []}

            resp = await client.get(f"/api/v1/boundaries/{mock_boundary.id}")

        assert resp.status_code == 200
        data = resp.json()
        # Zero-total stats are still included (not null)
        assert data["voter_stats"] is not None
        assert data["voter_stats"]["total"] == 0
        assert data["voter_stats"]["by_status"] == []
