"""Integration tests for the batch boundary check endpoint.

Tests POST /api/v1/voters/{voter_id}/geocode/check-boundaries.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.voters import voters_router

from .conftest import make_test_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_analyst_user() -> MagicMock:
    """Mock analyst user for dependency override."""
    user = MagicMock()
    user.role = "analyst"
    user.id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    user.username = "analyst"
    user.is_active = True
    return user


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Minimal FastAPI app with voters router (no auth override)."""
    return make_test_app(voters_router, mock_session)


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    return make_test_app(voters_router, mock_session, user=mock_admin_user)


@pytest.fixture
def analyst_app(mock_session: AsyncMock, mock_analyst_user: MagicMock) -> FastAPI:
    """FastAPI app with analyst auth."""
    return make_test_app(voters_router, mock_session, user=mock_analyst_user)


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """FastAPI app with viewer auth."""
    return make_test_app(voters_router, mock_session, user=mock_viewer_user)


@pytest.fixture
async def analyst_client(analyst_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async test client with analyst auth."""
    async with AsyncClient(
        transport=ASGITransport(app=analyst_app),
        base_url="https://test",
        follow_redirects=False,
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_VOTER_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

_ENDPOINT = f"/api/v1/voters/{_VOTER_ID}/geocode/check-boundaries"


def _make_response(
    *,
    total_locations: int = 1,
    total_districts: int = 1,
    districts: list | None = None,
) -> dict:
    """Build a BatchBoundaryCheckResponse-shaped dict for mock returns."""
    return {
        "voter_id": str(_VOTER_ID),
        "districts": districts if districts is not None else [],
        "provider_summary": [],
        "total_locations": total_locations,
        "total_districts": total_districts,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def _make_district_with_providers(
    boundary_type: str = "congressional",
    boundary_identifier: str = "5",
    providers: list | None = None,
) -> dict:
    """Build a DistrictBoundaryResult-shaped dict."""
    return {
        "boundary_id": str(uuid.uuid4()),
        "boundary_type": boundary_type,
        "boundary_identifier": boundary_identifier,
        "has_geometry": True,
        "providers": providers if providers is not None else [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBatchBoundaryCheck:
    """Tests for POST /api/v1/voters/{voter_id}/geocode/check-boundaries."""

    async def test_admin_gets_200_with_correct_structure(self, admin_client) -> None:
        """Admin user receives 200 with a correctly shaped BatchBoundaryCheckResponse."""
        mock_result = _make_response()

        with patch(
            "voter_api.api.v1.voters.check_batch_boundaries_for_voter",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.post(_ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()
        assert body["voter_id"] == str(_VOTER_ID)
        assert isinstance(body["districts"], list)
        assert isinstance(body["provider_summary"], list)
        assert "total_locations" in body
        assert "total_districts" in body
        assert "checked_at" in body

    async def test_analyst_gets_403(self, analyst_client) -> None:
        """Analyst role cannot access admin-only endpoint — returns 403."""
        resp = await analyst_client.post(_ENDPOINT)
        assert resp.status_code == 403

    async def test_viewer_gets_403(self, viewer_client) -> None:
        """Viewer role cannot access admin-only endpoint — returns 403."""
        resp = await viewer_client.post(_ENDPOINT)
        assert resp.status_code == 403

    async def test_unauthenticated_gets_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        resp = await client.post(_ENDPOINT)
        assert resp.status_code == 401

    async def test_voter_not_found_returns_404(self, admin_client) -> None:
        """When service returns None, the endpoint raises 404."""
        with patch(
            "voter_api.api.v1.voters.check_batch_boundaries_for_voter",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.post(_ENDPOINT)

        assert resp.status_code == 404

    async def test_no_geocoded_locations_returns_200(self, admin_client) -> None:
        """Voter with no geocoded locations returns 200 with total_locations=0."""
        mock_result = _make_response(total_locations=0, total_districts=2)

        with patch(
            "voter_api.api.v1.voters.check_batch_boundaries_for_voter",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.post(_ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_locations"] == 0
        assert body["total_districts"] == 2

    async def test_no_districts_returns_200(self, admin_client) -> None:
        """Voter with no registered districts returns 200 with total_districts=0."""
        mock_result = _make_response(total_locations=2, total_districts=0)

        with patch(
            "voter_api.api.v1.voters.check_batch_boundaries_for_voter",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.post(_ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_districts"] == 0
        assert body["total_locations"] == 2

    async def test_provider_result_includes_determined_identifier_field(self, admin_client) -> None:
        """ProviderResult objects include determined_identifier key in response JSON."""
        providers = [
            {"source_type": "census", "is_contained": True, "determined_identifier": None},
            {"source_type": "google", "is_contained": False, "determined_identifier": "007"},
        ]
        mock_result = _make_response(
            total_locations=2,
            total_districts=1,
            districts=[_make_district_with_providers(providers=providers)],
        )

        with patch(
            "voter_api.api.v1.voters.check_batch_boundaries_for_voter",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.post(_ENDPOINT)

        assert resp.status_code == 200
        body = resp.json()
        district = body["districts"][0]
        assert len(district["providers"]) == 2

        by_source = {p["source_type"]: p for p in district["providers"]}

        # Contained provider: determined_identifier is None (absent or null)
        assert "determined_identifier" in by_source["census"]
        assert by_source["census"]["determined_identifier"] is None

        # Mismatch provider: determined_identifier populated
        assert by_source["google"]["determined_identifier"] == "007"
