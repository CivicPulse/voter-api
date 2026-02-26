"""Integration tests for candidate API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.candidates import candidates_router
from voter_api.api.v1.elections import elections_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.models.candidate import Candidate, CandidateLink
from voter_api.models.election import Election


def _make_election(**overrides) -> MagicMock:
    """Build a mock Election."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": "2026-02-17",
        "election_type": "special",
        "district": "District 5",
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


def _make_candidate(election_id: uuid.UUID | None = None, **overrides) -> MagicMock:
    """Build a mock Candidate."""
    defaults = {
        "id": uuid.uuid4(),
        "election_id": election_id or uuid.uuid4(),
        "full_name": "Andrea Cooke",
        "party": None,
        "bio": "Community advocate.",
        "photo_url": None,
        "ballot_order": 1,
        "filing_status": "qualified",
        "is_incumbent": False,
        "sos_ballot_option_id": None,
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
        "links": [],
    }
    defaults.update(overrides)
    candidate = MagicMock(spec=Candidate)
    for k, v in defaults.items():
        setattr(candidate, k, v)
    return candidate


def _make_link(candidate_id: uuid.UUID | None = None, **overrides) -> MagicMock:
    """Build a mock CandidateLink."""
    defaults = {
        "id": uuid.uuid4(),
        "candidate_id": candidate_id or uuid.uuid4(),
        "link_type": "campaign",
        "url": "https://cooke2026.com",
        "label": "Campaign Website",
        "created_at": datetime(2026, 2, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    link = MagicMock(spec=CandidateLink)
    for k, v in defaults.items():
        setattr(link, k, v)
    return link


@pytest.fixture
def mock_session():
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
def mock_viewer_user():
    user = MagicMock()
    user.role = "viewer"
    user.id = "viewer-user-id"
    user.username = "viewer"
    user.is_active = True
    return user


@pytest.fixture
def app(mock_session) -> FastAPI:
    """Minimal FastAPI app with candidates + elections routers (no auth)."""
    app = FastAPI()
    app.include_router(candidates_router, prefix="/api/v1")
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_app(mock_session, mock_admin_user) -> FastAPI:
    """FastAPI app with admin auth."""
    app = FastAPI()
    app.include_router(candidates_router, prefix="/api/v1")
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
def viewer_app(mock_session, mock_viewer_user) -> FastAPI:
    """FastAPI app with viewer auth."""
    app = FastAPI()
    app.include_router(candidates_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        yield c


@pytest.fixture
async def admin_client(admin_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=admin_app), base_url="https://test") as c:
        yield c


@pytest.fixture
async def viewer_client(viewer_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=viewer_app), base_url="https://test") as c:
        yield c


# --- GET /elections/{election_id}/candidates ---


class TestListCandidates:
    @pytest.mark.asyncio
    async def test_empty_election_returns_empty_list(self, client):
        election = _make_election()
        with (
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
            patch("voter_api.services.candidate_service.list_candidates", return_value=([], 0)),
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/candidates")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_candidates_with_pagination(self, client):
        election = _make_election()
        candidate = _make_candidate(election_id=election.id)
        with (
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
            patch("voter_api.services.candidate_service.list_candidates", return_value=([candidate], 1)),
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/candidates")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["full_name"] == "Andrea Cooke"
        assert data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_status_filter(self, client):
        election = _make_election()
        with (
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
            patch("voter_api.services.candidate_service.list_candidates", return_value=([], 0)) as mock_list,
        ):
            await client.get(f"/api/v1/elections/{election.id}/candidates?status=withdrawn")

        mock_list.assert_awaited_once()
        assert mock_list.call_args[1]["status"] == "withdrawn"

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_election(self, client):
        with patch("voter_api.services.election_service.get_election_by_id", return_value=None):
            resp = await client.get(f"/api/v1/elections/{uuid.uuid4()}/candidates")
        assert resp.status_code == 404


# --- GET /candidates/{candidate_id} ---


class TestGetCandidate:
    @pytest.mark.asyncio
    async def test_returns_candidate_detail(self, client):
        from voter_api.schemas.candidate import CandidateDetailResponse, CandidateLinkResponse

        candidate_id = uuid.uuid4()
        mock_response = CandidateDetailResponse(
            id=candidate_id,
            election_id=uuid.uuid4(),
            full_name="Andrea Cooke",
            filing_status="qualified",
            is_incumbent=False,
            created_at=datetime(2026, 2, 1, tzinfo=UTC),
            updated_at=datetime(2026, 2, 1, tzinfo=UTC),
            links=[
                CandidateLinkResponse(id=uuid.uuid4(), link_type="campaign", url="https://cooke.com"),
            ],
        )

        with patch("voter_api.services.candidate_service.get_candidate_with_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/candidates/{candidate_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == "Andrea Cooke"
        assert len(data["links"]) == 1

    @pytest.mark.asyncio
    async def test_404_for_nonexistent_candidate(self, client):
        with patch("voter_api.services.candidate_service.get_candidate_with_results", return_value=None):
            resp = await client.get(f"/api/v1/candidates/{uuid.uuid4()}")
        assert resp.status_code == 404


# --- POST /elections/{election_id}/candidates ---


class TestCreateCandidate:
    @pytest.mark.asyncio
    async def test_create_returns_201(self, admin_client):
        election = _make_election()
        candidate = _make_candidate(election_id=election.id)
        with (
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
            patch("voter_api.services.candidate_service.create_candidate", return_value=candidate),
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{election.id}/candidates",
                json={"full_name": "Andrea Cooke"},
            )
        assert resp.status_code == 201
        assert resp.json()["full_name"] == "Andrea Cooke"

    @pytest.mark.asyncio
    async def test_duplicate_name_returns_409(self, admin_client):
        election = _make_election()
        with (
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
            patch(
                "voter_api.services.candidate_service.create_candidate",
                side_effect=ValueError("already exists"),
            ),
        ):
            resp = await admin_client.post(
                f"/api/v1/elections/{election.id}/candidates",
                json={"full_name": "Andrea Cooke"},
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_nonexistent_election_returns_404(self, admin_client):
        with patch("voter_api.services.election_service.get_election_by_id", return_value=None):
            resp = await admin_client.post(
                f"/api/v1/elections/{uuid.uuid4()}/candidates",
                json={"full_name": "Test"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.post(
            f"/api/v1/elections/{uuid.uuid4()}/candidates",
            json={"full_name": "Test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_gets_403(self, viewer_client):
        resp = await viewer_client.post(
            f"/api/v1/elections/{uuid.uuid4()}/candidates",
            json={"full_name": "Test"},
        )
        assert resp.status_code == 403


# --- PATCH /candidates/{candidate_id} ---


class TestUpdateCandidate:
    @pytest.mark.asyncio
    async def test_update_returns_200(self, admin_client):
        candidate = _make_candidate(filing_status="withdrawn")
        with patch("voter_api.services.candidate_service.update_candidate", return_value=candidate):
            resp = await admin_client.patch(
                f"/api/v1/candidates/{candidate.id}",
                json={"filing_status": "withdrawn"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_404(self, admin_client):
        with patch("voter_api.services.candidate_service.update_candidate", return_value=None):
            resp = await admin_client.patch(
                f"/api/v1/candidates/{uuid.uuid4()}",
                json={"filing_status": "withdrawn"},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_conflict_409(self, admin_client):
        with patch(
            "voter_api.services.candidate_service.update_candidate",
            side_effect=ValueError("name conflict"),
        ):
            resp = await admin_client.patch(
                f"/api/v1/candidates/{uuid.uuid4()}",
                json={"full_name": "Conflict Name"},
            )
        assert resp.status_code == 409


# --- DELETE /candidates/{candidate_id} ---


class TestDeleteCandidate:
    @pytest.mark.asyncio
    async def test_delete_returns_204(self, admin_client):
        with patch("voter_api.services.candidate_service.delete_candidate", return_value=True):
            resp = await admin_client.delete(f"/api/v1/candidates/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_404(self, admin_client):
        with patch("voter_api.services.candidate_service.delete_candidate", return_value=False):
            resp = await admin_client.delete(f"/api/v1/candidates/{uuid.uuid4()}")
        assert resp.status_code == 404


# --- POST /candidates/{candidate_id}/links ---


class TestAddCandidateLink:
    @pytest.mark.asyncio
    async def test_add_link_returns_201(self, admin_client):
        candidate_id = uuid.uuid4()
        link = _make_link(candidate_id=candidate_id)
        with patch("voter_api.services.candidate_service.add_candidate_link", return_value=link):
            resp = await admin_client.post(
                f"/api/v1/candidates/{candidate_id}/links",
                json={"link_type": "campaign", "url": "https://cooke.com"},
            )
        assert resp.status_code == 201
        assert resp.json()["link_type"] == "campaign"

    @pytest.mark.asyncio
    async def test_add_link_candidate_not_found(self, admin_client):
        with patch("voter_api.services.candidate_service.add_candidate_link", return_value=None):
            resp = await admin_client.post(
                f"/api/v1/candidates/{uuid.uuid4()}/links",
                json={"link_type": "website", "url": "https://example.com"},
            )
        assert resp.status_code == 404


# --- DELETE /candidates/{candidate_id}/links/{link_id} ---


class TestDeleteCandidateLink:
    @pytest.mark.asyncio
    async def test_delete_link_returns_204(self, admin_client):
        with patch("voter_api.services.candidate_service.delete_candidate_link", return_value=True):
            resp = await admin_client.delete(f"/api/v1/candidates/{uuid.uuid4()}/links/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_link_not_found(self, admin_client):
        with patch("voter_api.services.candidate_service.delete_candidate_link", return_value=False):
            resp = await admin_client.delete(f"/api/v1/candidates/{uuid.uuid4()}/links/{uuid.uuid4()}")
        assert resp.status_code == 404


# --- SOS Results Cross-Reference ---


class TestSosResultsCrossReference:
    @pytest.mark.asyncio
    async def test_candidate_with_matching_sos_id(self, client):
        from voter_api.schemas.candidate import CandidateDetailResponse

        candidate_id = uuid.uuid4()
        mock_response = CandidateDetailResponse(
            id=candidate_id,
            election_id=uuid.uuid4(),
            full_name="John Smith",
            filing_status="qualified",
            is_incumbent=False,
            sos_ballot_option_id="opt-123",
            created_at=datetime(2026, 2, 1, tzinfo=UTC),
            updated_at=datetime(2026, 2, 1, tzinfo=UTC),
            links=[],
            result_vote_count=5678,
            result_political_party="Rep",
        )

        with patch("voter_api.services.candidate_service.get_candidate_with_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/candidates/{candidate_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["result_vote_count"] == 5678
        assert data["result_political_party"] == "Rep"

    @pytest.mark.asyncio
    async def test_candidate_without_match_returns_null(self, client):
        from voter_api.schemas.candidate import CandidateDetailResponse

        candidate_id = uuid.uuid4()
        mock_response = CandidateDetailResponse(
            id=candidate_id,
            election_id=uuid.uuid4(),
            full_name="Jane Doe",
            filing_status="qualified",
            is_incumbent=False,
            created_at=datetime(2026, 2, 1, tzinfo=UTC),
            updated_at=datetime(2026, 2, 1, tzinfo=UTC),
            links=[],
        )

        with patch("voter_api.services.candidate_service.get_candidate_with_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/candidates/{candidate_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["result_vote_count"] is None
        assert data["result_political_party"] is None
