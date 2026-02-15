"""Unit tests for elected officials API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elected_officials import elected_officials_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_admin_user() -> MagicMock:
    """Create a mock admin user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testadmin"
    user.role = "admin"
    user.is_active = True
    return user


def _mock_official(
    *,
    boundary_type: str = "congressional",
    district_identifier: str = "5",
    full_name: str = "Nikema Williams",
    status: str = "approved",
) -> MagicMock:
    """Create a mock ElectedOfficial."""
    official = MagicMock()
    official.id = uuid.uuid4()
    official.boundary_type = boundary_type
    official.district_identifier = district_identifier
    official.full_name = full_name
    official.first_name = full_name.split()[0]
    official.last_name = full_name.split()[-1]
    official.party = "Democratic"
    official.title = "U.S. Representative"
    official.photo_url = None
    official.status = status
    official.term_start_date = None
    official.term_end_date = None
    official.last_election_date = None
    official.next_election_date = None
    official.website = "https://example.com"
    official.email = None
    official.phone = None
    official.office_address = None
    official.external_ids = None
    official.approved_by_id = None
    official.approved_at = None
    official.created_at = datetime.now(UTC)
    official.updated_at = datetime.now(UTC)
    official.sources = []
    return official


def _mock_source() -> MagicMock:
    """Create a mock ElectedOfficialSource."""
    source = MagicMock()
    source.id = uuid.uuid4()
    source.source_name = "open_states"
    source.source_record_id = "ocd-person/abc-123"
    source.boundary_type = "congressional"
    source.district_identifier = "5"
    source.full_name = "Nikema Williams"
    source.first_name = "Nikema"
    source.last_name = "Williams"
    source.party = "Democratic"
    source.title = "U.S. Representative"
    source.photo_url = None
    source.term_start_date = None
    source.term_end_date = None
    source.website = None
    source.email = None
    source.phone = None
    source.office_address = None
    source.fetched_at = datetime.now(UTC)
    source.is_current = True
    source.created_at = datetime.now(UTC)
    return source


@pytest.fixture
def admin_user() -> MagicMock:
    return _mock_admin_user()


@pytest.fixture
def app(admin_user: MagicMock) -> FastAPI:
    """Create minimal FastAPI app with elected officials router and mocked deps."""
    test_app = FastAPI()
    test_app.include_router(elected_officials_router, prefix="/api/v1")
    test_app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_current_user] = lambda: admin_user
    return test_app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    """Create async test client."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestListAllOfficials:
    """Tests for GET /api/v1/elected-officials."""

    @pytest.mark.asyncio
    async def test_returns_paginated_response(self, client: AsyncClient) -> None:
        """List endpoint returns 200 with pagination."""
        mock_official = _mock_official()
        with patch(
            "voter_api.api.v1.elected_officials.list_officials",
            new_callable=AsyncMock,
            return_value=([mock_official], 1),
        ):
            resp = await client.get("/api/v1/elected-officials")

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["full_name"] == "Nikema Williams"
        assert data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_empty_list(self, client: AsyncClient) -> None:
        """Returns empty items when no officials exist."""
        with patch(
            "voter_api.api.v1.elected_officials.list_officials",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await client.get("/api/v1/elected-officials")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["total_pages"] == 0

    @pytest.mark.asyncio
    async def test_passes_filters_to_service(self, client: AsyncClient) -> None:
        """Query params are forwarded to list_officials."""
        with patch(
            "voter_api.api.v1.elected_officials.list_officials",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_list:
            await client.get(
                "/api/v1/elected-officials",
                params={
                    "boundary_type": "congressional",
                    "district_identifier": "5",
                    "party": "Democratic",
                    "status": "approved",
                },
            )

        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs.kwargs["boundary_type"] == "congressional"
        assert call_kwargs.kwargs["district_identifier"] == "5"
        assert call_kwargs.kwargs["party"] == "Democratic"
        assert call_kwargs.kwargs["status"] == "approved"


class TestOfficialsByDistrict:
    """Tests for GET /api/v1/elected-officials/by-district."""

    @pytest.mark.asyncio
    async def test_returns_officials_for_district(self, client: AsyncClient) -> None:
        """Returns detail list for a specific district."""
        mock_official = _mock_official()
        with patch(
            "voter_api.api.v1.elected_officials.get_officials_for_district",
            new_callable=AsyncMock,
            return_value=[mock_official],
        ):
            resp = await client.get(
                "/api/v1/elected-officials/by-district",
                params={"boundary_type": "congressional", "district_identifier": "5"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["full_name"] == "Nikema Williams"

    @pytest.mark.asyncio
    async def test_requires_boundary_type(self, client: AsyncClient) -> None:
        """Missing boundary_type returns 422."""
        resp = await client.get(
            "/api/v1/elected-officials/by-district",
            params={"district_identifier": "5"},
        )
        assert resp.status_code == 422


class TestGetOfficialDetail:
    """Tests for GET /api/v1/elected-officials/{id}."""

    @pytest.mark.asyncio
    async def test_returns_detail(self, client: AsyncClient) -> None:
        """Returns full detail for an official."""
        mock_official = _mock_official()
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=mock_official,
        ):
            resp = await client.get(f"/api/v1/elected-officials/{mock_official.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "Nikema Williams"
        assert "sources" in data

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent official."""
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get(f"/api/v1/elected-officials/{uuid.uuid4()}")

        assert resp.status_code == 404


class TestGetOfficialSources:
    """Tests for GET /api/v1/elected-officials/{id}/sources."""

    @pytest.mark.asyncio
    async def test_returns_sources(self, client: AsyncClient) -> None:
        """Returns source records linked to an official."""
        mock_official = _mock_official()
        mock_official.sources = [_mock_source()]
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=mock_official,
        ):
            resp = await client.get(f"/api/v1/elected-officials/{mock_official.id}/sources")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source_name"] == "open_states"

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Returns 404 when official not found."""
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.get(f"/api/v1/elected-officials/{uuid.uuid4()}/sources")

        assert resp.status_code == 404


class TestCreateOfficialEndpoint:
    """Tests for POST /api/v1/elected-officials."""

    @pytest.mark.asyncio
    async def test_creates_official(self, client: AsyncClient) -> None:
        """Admin can create a new official."""
        mock_official = _mock_official(status="manual")
        with patch(
            "voter_api.api.v1.elected_officials.create_official",
            new_callable=AsyncMock,
            return_value=mock_official,
        ):
            resp = await client.post(
                "/api/v1/elected-officials",
                json={
                    "boundary_type": "congressional",
                    "district_identifier": "5",
                    "full_name": "Nikema Williams",
                    "party": "Democratic",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["full_name"] == "Nikema Williams"

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, client: AsyncClient) -> None:
        """Missing required fields returns 422."""
        resp = await client.post(
            "/api/v1/elected-officials",
            json={"boundary_type": "congressional"},
        )
        assert resp.status_code == 422


class TestUpdateOfficialEndpoint:
    """Tests for PATCH /api/v1/elected-officials/{id}."""

    @pytest.mark.asyncio
    async def test_updates_official(self, client: AsyncClient) -> None:
        """Admin can update an official."""
        mock_official = _mock_official()
        with (
            patch(
                "voter_api.api.v1.elected_officials.get_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
            patch(
                "voter_api.api.v1.elected_officials.update_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
        ):
            resp = await client.patch(
                f"/api/v1/elected-officials/{mock_official.id}",
                json={"party": "Republican"},
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent official."""
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.patch(
                f"/api/v1/elected-officials/{uuid.uuid4()}",
                json={"party": "Republican"},
            )

        assert resp.status_code == 404


class TestDeleteOfficialEndpoint:
    """Tests for DELETE /api/v1/elected-officials/{id}."""

    @pytest.mark.asyncio
    async def test_deletes_official(self, client: AsyncClient) -> None:
        """Admin can delete an official."""
        mock_official = _mock_official()
        with (
            patch(
                "voter_api.api.v1.elected_officials.get_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
            patch(
                "voter_api.api.v1.elected_officials.delete_official",
                new_callable=AsyncMock,
            ),
        ):
            resp = await client.delete(f"/api/v1/elected-officials/{mock_official.id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent official."""
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.delete(f"/api/v1/elected-officials/{uuid.uuid4()}")

        assert resp.status_code == 404


class TestApproveOfficialEndpoint:
    """Tests for POST /api/v1/elected-officials/{id}/approve."""

    @pytest.mark.asyncio
    async def test_approves_official(self, client: AsyncClient) -> None:
        """Admin can approve an official."""
        mock_official = _mock_official(status="approved")
        with (
            patch(
                "voter_api.api.v1.elected_officials.get_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
            patch(
                "voter_api.api.v1.elected_officials.approve_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
        ):
            resp = await client.post(
                f"/api/v1/elected-officials/{mock_official.id}/approve",
                json={},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent official."""
        with patch(
            "voter_api.api.v1.elected_officials.get_official",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.post(
                f"/api/v1/elected-officials/{uuid.uuid4()}/approve",
                json={},
            )

        assert resp.status_code == 404


class TestCreateOfficialEndpointErrors:
    """Tests for error handling on POST /api/v1/elected-officials."""

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_409(self, client: AsyncClient) -> None:
        """Service ValueError (duplicate) returns 409 Conflict."""
        with patch(
            "voter_api.api.v1.elected_officials.create_official",
            new_callable=AsyncMock,
            side_effect=ValueError("already exists"),
        ):
            resp = await client.post(
                "/api/v1/elected-officials",
                json={
                    "boundary_type": "congressional",
                    "district_identifier": "5",
                    "full_name": "Nikema Williams",
                },
            )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_unexpected_error_returns_500(self, client: AsyncClient) -> None:
        """Unexpected service exception returns 500."""
        with patch(
            "voter_api.api.v1.elected_officials.create_official",
            new_callable=AsyncMock,
            side_effect=RuntimeError("db connection lost"),
        ):
            resp = await client.post(
                "/api/v1/elected-officials",
                json={
                    "boundary_type": "congressional",
                    "district_identifier": "5",
                    "full_name": "Nikema Williams",
                },
            )

        assert resp.status_code == 500


class TestUpdateOfficialEndpointErrors:
    """Tests for error handling on PATCH /api/v1/elected-officials/{id}."""

    @pytest.mark.asyncio
    async def test_update_value_error_returns_422(self, client: AsyncClient) -> None:
        """Service ValueError returns 422."""
        mock_official = _mock_official()
        with (
            patch(
                "voter_api.api.v1.elected_officials.get_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
            patch(
                "voter_api.api.v1.elected_officials.update_official",
                new_callable=AsyncMock,
                side_effect=ValueError("invalid update"),
            ),
        ):
            resp = await client.patch(
                f"/api/v1/elected-officials/{mock_official.id}",
                json={"party": "Republican"},
            )

        assert resp.status_code == 422
        assert "invalid update" in resp.json()["detail"]


class TestApproveOfficialEndpointErrors:
    """Tests for error handling on POST /api/v1/elected-officials/{id}/approve."""

    @pytest.mark.asyncio
    async def test_approve_with_invalid_source_returns_422(self, client: AsyncClient) -> None:
        """Service ValueError on bad source_id returns 422."""
        mock_official = _mock_official(status="auto")
        with (
            patch(
                "voter_api.api.v1.elected_officials.get_official",
                new_callable=AsyncMock,
                return_value=mock_official,
            ),
            patch(
                "voter_api.api.v1.elected_officials.approve_official",
                new_callable=AsyncMock,
                side_effect=ValueError("Source record not found"),
            ),
        ):
            resp = await client.post(
                f"/api/v1/elected-officials/{mock_official.id}/approve",
                json={"source_id": str(uuid.uuid4())},
            )

        assert resp.status_code == 422
        assert "Source record not found" in resp.json()["detail"]


class TestGetDistrictSources:
    """Tests for GET /api/v1/elected-officials/district/{type}/{id}/sources."""

    @pytest.mark.asyncio
    async def test_returns_sources(self, client: AsyncClient) -> None:
        """Admin can list sources for a district."""
        mock_source = _mock_source()
        with patch(
            "voter_api.api.v1.elected_officials.list_sources_for_district",
            new_callable=AsyncMock,
            return_value=[mock_source],
        ):
            resp = await client.get("/api/v1/elected-officials/district/congressional/5/sources")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["source_name"] == "open_states"


# ---------------------------------------------------------------------------
# Auth enforcement tests
# ---------------------------------------------------------------------------


def _mock_viewer_user() -> MagicMock:
    """Create a mock viewer user (non-admin)."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = "testviewer"
    user.role = "viewer"
    user.is_active = True
    return user


@pytest.fixture
def viewer_app() -> FastAPI:
    """Create FastAPI app with a viewer-role user (not admin)."""
    test_app = FastAPI()
    test_app.include_router(elected_officials_router, prefix="/api/v1")
    test_app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    test_app.dependency_overrides[get_current_user] = _mock_viewer_user
    return test_app


@pytest.fixture
def viewer_client(viewer_app: FastAPI) -> AsyncClient:
    """Create async test client with viewer-role user."""
    return AsyncClient(transport=ASGITransport(app=viewer_app), base_url="http://test")


class TestAuthEnforcement:
    """Tests that admin-only endpoints reject viewer-role users."""

    @pytest.mark.asyncio
    async def test_create_requires_admin_role(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot create officials — returns 403."""
        resp = await viewer_client.post(
            "/api/v1/elected-officials",
            json={
                "boundary_type": "congressional",
                "district_identifier": "5",
                "full_name": "Nikema Williams",
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_requires_admin_role(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot update officials — returns 403."""
        resp = await viewer_client.patch(
            f"/api/v1/elected-officials/{uuid.uuid4()}",
            json={"party": "Republican"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_requires_admin_role(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot delete officials — returns 403."""
        resp = await viewer_client.delete(f"/api/v1/elected-officials/{uuid.uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_approve_requires_admin_role(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot approve officials — returns 403."""
        resp = await viewer_client.post(
            f"/api/v1/elected-officials/{uuid.uuid4()}/approve",
            json={},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_district_sources_requires_admin_role(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot access district sources — returns 403."""
        resp = await viewer_client.get("/api/v1/elected-officials/district/congressional/5/sources")
        assert resp.status_code == 403
