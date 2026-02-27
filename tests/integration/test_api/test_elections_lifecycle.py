"""Integration tests for election lifecycle API endpoints.

Covers:
- US1: Soft-delete (DELETE /elections/{id})
- US2: Manual creation (POST /elections with source='manual')
- US3: Link-to-feed (POST /elections/{id}/link)
- US4: Source filter (GET /elections?source=...)
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elections import elections_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.models.election import Election
from voter_api.schemas.election import ElectionSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_election(**overrides: object) -> MagicMock:
    """Build a mock Election model instance with lifecycle fields."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": date(2026, 3, 1),
        "election_type": "special",
        "district": "State Senate - District 18",
        "data_source_url": None,
        "source": "manual",
        "status": "active",
        "last_refreshed_at": None,
        "refresh_interval_seconds": 120,
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
        "deleted_at": None,
        "ballot_item_id": None,
        "boundary_id": uuid.uuid4(),
        "district_type": None,
        "district_identifier": None,
        "district_party": None,
        "result": None,
        "county_results": [],
        "description": None,
        "purpose": None,
        "eligibility_description": None,
        "registration_deadline": None,
        "early_voting_start": None,
        "early_voting_end": None,
        "absentee_request_deadline": None,
        "qualifying_start": None,
        "qualifying_end": None,
    }
    defaults.update(overrides)
    election = MagicMock(spec=Election)
    for k, v in defaults.items():
        setattr(election, k, v)
    return election


def _make_election_summary(**overrides: object) -> ElectionSummary:
    """Build an ElectionSummary schema instance."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": date(2026, 3, 1),
        "election_type": "special",
        "district": "State Senate - District 18",
        "status": "active",
        "source": "manual",
        "last_refreshed_at": None,
    }
    defaults.update(overrides)
    return ElectionSummary(**defaults)


def _make_mock_user(role: str = "admin") -> MagicMock:
    """Build a mock User with the given role."""
    user = MagicMock()
    user.role = role
    user.id = uuid.uuid4()
    user.username = f"test_{role}"
    user.is_active = True
    return user


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_admin_user() -> MagicMock:
    return _make_mock_user("admin")


@pytest.fixture
def mock_viewer_user() -> MagicMock:
    return _make_mock_user("viewer")


@pytest.fixture
def public_app(mock_session: AsyncMock) -> FastAPI:
    """FastAPI app with elections router and no auth override (unauthenticated)."""
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """FastAPI app with viewer auth."""
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    return app


@pytest.fixture
async def public_client(public_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=public_app), base_url="https://test") as client:
        yield client


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=admin_app), base_url="https://test") as client:
        yield client


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=viewer_app), base_url="https://test") as client:
        yield client


# ---------------------------------------------------------------------------
# US1: Soft-Delete
# ---------------------------------------------------------------------------


class TestSoftDeleteElection:
    """Tests for DELETE /elections/{id}."""

    @pytest.mark.asyncio
    async def test_delete_election_admin_returns_204(self, admin_client: AsyncClient) -> None:
        """Admin can soft-delete an election, returns 204."""
        election_id = uuid.uuid4()
        with patch(
            "voter_api.api.v1.elections.soft_delete_election",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = await admin_client.delete(f"/api/v1/elections/{election_id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_election_viewer_returns_403(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot soft-delete an election, returns 403."""
        election_id = uuid.uuid4()
        resp = await viewer_client.delete(f"/api/v1/elections/{election_id}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_election_unauthenticated_returns_401(self, public_client: AsyncClient) -> None:
        """Unauthenticated request to DELETE returns 401."""
        election_id = uuid.uuid4()
        resp = await public_client.delete(f"/api/v1/elections/{election_id}")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_election_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        """Attempting to delete a non-existent election returns 404."""
        fake_id = uuid.uuid4()
        with patch(
            "voter_api.api.v1.elections.soft_delete_election",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = await admin_client.delete(f"/api/v1/elections/{fake_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_election_already_deleted_returns_404(self, admin_client: AsyncClient) -> None:
        """Soft-deleting an already soft-deleted election returns 404."""
        election_id = uuid.uuid4()
        # soft_delete_election returns False when election is already deleted or not found
        with patch(
            "voter_api.api.v1.elections.soft_delete_election",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = await admin_client.delete(f"/api/v1/elections/{election_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_election_not_in_list(self, public_client: AsyncClient) -> None:
        """A soft-deleted election does not appear in GET /elections."""
        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await public_client.get("/api/v1/elections")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_deleted_election_detail_returns_404(self, public_client: AsyncClient) -> None:
        """GET /elections/{id} returns 404 for a soft-deleted election."""
        election_id = uuid.uuid4()
        with patch(
            "voter_api.services.election_service.get_election_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await public_client.get(f"/api/v1/elections/{election_id}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_voter_history_preserved_after_election_soft_delete(self, admin_client: AsyncClient) -> None:
        """Soft-deleting an election does not affect voter_history rows.

        voter_history records have no FK to elections. They are joined at query
        time using (election_date, normalized_election_type). Soft-deleting an
        election only sets deleted_at on the elections row; voter_history rows
        are completely unaffected.
        """
        election_id = uuid.uuid4()

        with patch(
            "voter_api.api.v1.elections.soft_delete_election",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_soft_delete:
            resp = await admin_client.delete(f"/api/v1/elections/{election_id}")

        # Soft delete succeeded
        assert resp.status_code == 204
        mock_soft_delete.assert_awaited_once_with(
            mock_soft_delete.call_args[0][0],
            election_id,
        )
        # The voter_history rows would still exist with their election_id
        # (verified at DB level in E2E tests; here we confirm soft_delete_election
        # is called, not hard delete).


# ---------------------------------------------------------------------------
# US2: Manual Creation
# ---------------------------------------------------------------------------


class TestCreateManualElection:
    """Tests for POST /elections with source='manual'."""

    @pytest.mark.asyncio
    async def test_create_manual_election_success(self, admin_client: AsyncClient) -> None:
        """Admin can create a manual election with boundary_id, gets 201 with source='manual'."""
        boundary_id = uuid.uuid4()
        election = _make_election(source="manual", data_source_url=None, boundary_id=boundary_id)

        with patch(
            "voter_api.services.election_service.create_election",
            new_callable=AsyncMock,
            return_value=election,
        ):
            resp = await admin_client.post(
                "/api/v1/elections",
                json={
                    "name": "Manual Election",
                    "election_date": "2026-05-01",
                    "election_type": "special",
                    "district": "District 18",
                    "source": "manual",
                    "boundary_id": str(boundary_id),
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["source"] == "manual"
        assert data["data_source_url"] is None

    @pytest.mark.asyncio
    async def test_create_manual_election_without_boundary_returns_422(self, admin_client: AsyncClient) -> None:
        """Creating a manual election without boundary_id returns 422 (Pydantic validation)."""
        resp = await admin_client.post(
            "/api/v1/elections",
            json={
                "name": "Manual Election",
                "election_date": "2026-05-01",
                "election_type": "special",
                "district": "District 18",
                "source": "manual",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_manual_election_invalid_boundary_returns_422(self, admin_client: AsyncClient) -> None:
        """Creating a manual election with a non-existent boundary_id returns 422."""
        boundary_id = uuid.uuid4()

        with patch(
            "voter_api.services.election_service.create_election",
            new_callable=AsyncMock,
            side_effect=ValueError(f"Boundary {boundary_id} not found"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections",
                json={
                    "name": "Manual Election",
                    "election_date": "2026-05-01",
                    "election_type": "special",
                    "district": "District 18",
                    "source": "manual",
                    "boundary_id": str(boundary_id),
                },
            )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_sos_feed_election_without_url_returns_422(self, admin_client: AsyncClient) -> None:
        """Creating a sos_feed election without data_source_url returns 422."""
        resp = await admin_client.post(
            "/api/v1/elections",
            json={
                "name": "SOS Election",
                "election_date": "2026-05-01",
                "election_type": "special",
                "district": "District 18",
                "source": "sos_feed",
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# US3: Link-to-Feed
# ---------------------------------------------------------------------------


class TestLinkElection:
    """Tests for POST /elections/{id}/link."""

    @pytest.mark.asyncio
    async def test_link_election_admin_returns_200(self, admin_client: AsyncClient) -> None:
        """Admin can link a manual election to a feed URL, gets 200 with source='linked'."""
        election = _make_election(source="linked", data_source_url="https://results.sos.ga.gov/feed.json")

        with patch(
            "voter_api.services.election_service.link_election",
            new_callable=AsyncMock,
            return_value=election,
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{election.id}/link",
                json={
                    "data_source_url": "https://results.sos.ga.gov/feed.json",
                    "ballot_item_id": "S18",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "linked"

    @pytest.mark.asyncio
    async def test_link_election_non_manual_returns_400(self, admin_client: AsyncClient) -> None:
        """Linking a non-manual election raises ValueError -> 400."""
        election_id = uuid.uuid4()

        with patch(
            "voter_api.services.election_service.link_election",
            new_callable=AsyncMock,
            side_effect=ValueError("Only manual elections can be linked to a feed."),
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{election_id}/link",
                json={
                    "data_source_url": "https://results.sos.ga.gov/feed.json",
                },
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_link_election_duplicate_feed_returns_409(self, admin_client: AsyncClient) -> None:
        """Linking when another election already claims the same feed+ballot_item returns 409."""
        from voter_api.services.election_service import DuplicateElectionError

        election_id = uuid.uuid4()

        with patch(
            "voter_api.services.election_service.link_election",
            new_callable=AsyncMock,
            side_effect=DuplicateElectionError("Another election already linked to this feed ballot item."),
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{election_id}/link",
                json={
                    "data_source_url": "https://results.sos.ga.gov/feed.json",
                    "ballot_item_id": "S18",
                },
            )

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_link_election_not_found_returns_404(self, admin_client: AsyncClient) -> None:
        """Linking a non-existent election returns 404."""
        fake_id = uuid.uuid4()

        with patch(
            "voter_api.services.election_service.link_election",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{fake_id}/link",
                json={
                    "data_source_url": "https://results.sos.ga.gov/feed.json",
                },
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_link_election_viewer_returns_403(self, viewer_client: AsyncClient) -> None:
        """Viewer cannot link an election, returns 403."""
        election_id = uuid.uuid4()
        resp = await viewer_client.post(
            f"/api/v1/elections/{election_id}/link",
            json={
                "data_source_url": "https://results.sos.ga.gov/feed.json",
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# US4: Source Filter
# ---------------------------------------------------------------------------


class TestListElectionsSourceFilter:
    """Tests for GET /elections?source=... filter."""

    @pytest.mark.asyncio
    async def test_list_elections_source_filter_sos_feed(self, public_client: AsyncClient) -> None:
        """GET /elections?source=sos_feed returns only sos_feed elections."""
        sos_election = _make_election_summary(source="sos_feed")

        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
            return_value=([sos_election], 1),
        ) as mock_list:
            resp = await public_client.get("/api/v1/elections?source=sos_feed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 1
        assert data["items"][0]["source"] == "sos_feed"
        # Confirm the source kwarg was passed to the service
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("source") == "sos_feed"

    @pytest.mark.asyncio
    async def test_list_elections_source_filter_manual(self, public_client: AsyncClient) -> None:
        """GET /elections?source=manual returns only manual elections."""
        manual_election = _make_election_summary(source="manual")

        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
            return_value=([manual_election], 1),
        ) as mock_list:
            resp = await public_client.get("/api/v1/elections?source=manual")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["source"] == "manual"
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("source") == "manual"

    @pytest.mark.asyncio
    async def test_list_elections_source_filter_linked(self, public_client: AsyncClient) -> None:
        """GET /elections?source=linked returns only linked elections."""
        linked_election = _make_election_summary(
            source="linked",
        )

        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
            return_value=([linked_election], 1),
        ) as mock_list:
            resp = await public_client.get("/api/v1/elections?source=linked")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["source"] == "linked"
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs.get("source") == "linked"

    @pytest.mark.asyncio
    async def test_list_elections_source_filter_empty_result(self, public_client: AsyncClient) -> None:
        """GET /elections?source=manual returns empty list when no manual elections exist."""
        with patch(
            "voter_api.services.election_service.list_elections",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await public_client.get("/api/v1/elections?source=manual")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["total"] == 0
        assert data["items"] == []
