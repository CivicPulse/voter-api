"""Integration tests for election metadata enrichment (010-election-info).

Tests election detail response with new metadata fields and milestone date filters.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elections import elections_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.models.election import Election


def _make_election(**overrides) -> MagicMock:
    """Build a mock Election with metadata fields."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": date(2026, 3, 17),
        "election_type": "special",
        "district": "Commission District 5",
        "status": "active",
        "data_source_url": "https://example.com/feed.json",
        "refresh_interval_seconds": 120,
        "last_refreshed_at": None,
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
        "result": None,
        "ballot_item_id": None,
        "boundary_id": None,
        "district_type": None,
        "district_identifier": None,
        "district_party": None,
        # New metadata fields
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


@pytest.fixture
def mock_session():
    from unittest.mock import AsyncMock

    return AsyncMock()


@pytest.fixture
def mock_admin_user():
    user = MagicMock()
    user.role = "admin"
    user.id = "admin-user-id"
    user.username = "admin"
    user.is_active = True
    return user


@pytest.fixture
def app(mock_session) -> FastAPI:
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_app(mock_session, mock_admin_user) -> FastAPI:
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        yield c


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=admin_app), base_url="https://test") as c:
        yield c


# --- Election detail metadata tests (T014) ---


class TestElectionMetadataInDetail:
    """Verify election detail response includes new metadata fields."""

    @pytest.mark.asyncio
    async def test_detail_returns_metadata_when_populated(self, client):
        election = _make_election(
            description="Special election for Commission District 5.",
            purpose="Fill vacant seat",
            eligibility_description="Registered voters in District 5",
            registration_deadline=date(2026, 2, 16),
            early_voting_start=date(2026, 2, 25),
            early_voting_end=date(2026, 3, 13),
            absentee_request_deadline=date(2026, 3, 6),
            qualifying_start=datetime(2026, 2, 11, 12, 0, 0, tzinfo=UTC),
            qualifying_end=datetime(2026, 2, 13, 17, 30, 0, tzinfo=UTC),
        )

        with patch("voter_api.services.election_service.get_election_by_id", return_value=election):
            resp = await client.get(f"/api/v1/elections/{election.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Special election for Commission District 5."
        assert data["purpose"] == "Fill vacant seat"
        assert data["eligibility_description"] == "Registered voters in District 5"
        assert data["registration_deadline"] == "2026-02-16"
        assert data["early_voting_start"] == "2026-02-25"
        assert data["early_voting_end"] == "2026-03-13"
        assert data["absentee_request_deadline"] == "2026-03-06"
        assert data["qualifying_start"] is not None
        assert data["qualifying_end"] is not None

    @pytest.mark.asyncio
    async def test_detail_returns_null_metadata_when_not_set(self, client):
        election = _make_election()

        with patch("voter_api.services.election_service.get_election_by_id", return_value=election):
            resp = await client.get(f"/api/v1/elections/{election.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] is None
        assert data["purpose"] is None
        assert data["eligibility_description"] is None
        assert data["registration_deadline"] is None
        assert data["early_voting_start"] is None
        assert data["early_voting_end"] is None
        assert data["absentee_request_deadline"] is None
        assert data["qualifying_start"] is None
        assert data["qualifying_end"] is None

    @pytest.mark.asyncio
    async def test_backward_compatible_with_existing_fields(self, client):
        """Existing response fields are still present alongside new metadata."""
        election = _make_election()

        with patch("voter_api.services.election_service.get_election_by_id", return_value=election):
            resp = await client.get(f"/api/v1/elections/{election.id}")

        assert resp.status_code == 200
        data = resp.json()
        # Existing fields still present
        assert "name" in data
        assert "election_date" in data
        assert "election_type" in data
        assert "district" in data
        assert "status" in data
        assert "data_source_url" in data


# --- Election metadata update tests (T026) ---


class TestElectionMetadataUpdate:
    """Verify PATCH /elections/{id} accepts and persists new metadata fields."""

    @pytest.mark.asyncio
    async def test_update_with_metadata_fields(self, admin_client):
        election = _make_election(
            description="Updated description",
            purpose="Updated purpose",
        )

        with patch("voter_api.services.election_service.update_election", return_value=election):
            resp = await admin_client.patch(
                f"/api/v1/elections/{election.id}",
                json={
                    "description": "Updated description",
                    "purpose": "Updated purpose",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Updated description"
        assert data["purpose"] == "Updated purpose"

    @pytest.mark.asyncio
    async def test_update_metadata_backward_compatible(self, admin_client):
        """Updating existing fields still works with new metadata fields."""
        election = _make_election(status="finalized")

        with patch("voter_api.services.election_service.update_election", return_value=election):
            resp = await admin_client.patch(
                f"/api/v1/elections/{election.id}",
                json={"status": "finalized"},
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"


# --- Election list filters (T029) ---


class TestElectionMilestoneFilters:
    """Verify election list endpoint with new milestone date filters."""

    @pytest.mark.asyncio
    async def test_registration_open_filter(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get("/api/v1/elections?registration_open=true")

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        assert mock_list.call_args[1]["registration_open"] is True

    @pytest.mark.asyncio
    async def test_early_voting_active_filter(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get("/api/v1/elections?early_voting_active=true")

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        assert mock_list.call_args[1]["early_voting_active"] is True

    @pytest.mark.asyncio
    async def test_district_type_filter(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get("/api/v1/elections?district_type=county_commission")

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        assert mock_list.call_args[1]["district_type"] == "county_commission"

    @pytest.mark.asyncio
    async def test_district_identifier_filter(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get("/api/v1/elections?district_identifier=5")

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        assert mock_list.call_args[1]["district_identifier"] == "5"

    @pytest.mark.asyncio
    async def test_combined_filters(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get(
                "/api/v1/elections?registration_open=true&district_type=county_commission&district_identifier=5"
            )

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        kwargs = mock_list.call_args[1]
        assert kwargs["registration_open"] is True
        assert kwargs["district_type"] == "county_commission"
        assert kwargs["district_identifier"] == "5"
