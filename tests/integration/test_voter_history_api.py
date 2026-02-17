"""Integration tests for voter history API endpoints.

Covers:
- T018: POST /imports/voter-history (auth, file validation, 202 response)
- T025: GET /voters/{reg_num}/history (filtering, pagination, auth)
- T026: Voter detail enrichment with participation_summary
- T036: GET /elections/{id}/participation (filters, pagination, auth, 404)
- T037: GET /elections/{id}/participation/stats (counts, breakdowns, auth, 404)
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.imports import router as imports_router
from voter_api.api.v1.voter_history import voter_history_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.models.voter_history import VoterHistory
from voter_api.schemas.voter_history import (
    BallotStyleBreakdown,
    CountyBreakdown,
    ParticipationStatsResponse,
    ParticipationSummary,
)

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_user(role: str = "admin") -> MagicMock:
    """Build a mock User with the given role."""
    user = MagicMock()
    user.role = role
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.is_active = True
    return user


def _make_voter_history(**overrides: object) -> MagicMock:
    """Build a mock VoterHistory model instance."""
    defaults = {
        "id": uuid.uuid4(),
        "voter_registration_number": "12345678",
        "county": "FULTON",
        "election_date": date(2024, 11, 5),
        "election_type": "GENERAL ELECTION",
        "normalized_election_type": "general",
        "party": "NP",
        "ballot_style": "BALLOT 1",
        "absentee": False,
        "provisional": False,
        "supplemental": False,
        "import_job_id": uuid.uuid4(),
        "created_at": datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    record = MagicMock(spec=VoterHistory)
    for k, v in defaults.items():
        setattr(record, k, v)
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_admin_user():
    return _make_mock_user("admin")


@pytest.fixture
def mock_analyst_user():
    return _make_mock_user("analyst")


@pytest.fixture
def mock_viewer_user():
    return _make_mock_user("viewer")


@pytest.fixture
def admin_app(mock_session, mock_admin_user) -> FastAPI:
    """FastAPI app with admin auth and both routers."""
    app = FastAPI()
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(voter_history_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
def analyst_app(mock_session, mock_analyst_user) -> FastAPI:
    """FastAPI app with analyst auth."""
    app = FastAPI()
    app.include_router(voter_history_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_analyst_user
    return app


@pytest.fixture
def viewer_app(mock_session, mock_viewer_user) -> FastAPI:
    """FastAPI app with viewer auth (restricted)."""
    app = FastAPI()
    app.include_router(voter_history_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
    return app


@pytest.fixture
def unauth_app(mock_session) -> FastAPI:
    """FastAPI app with no auth override."""
    app = FastAPI()
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(voter_history_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_client(admin_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=admin_app), base_url="http://test")


@pytest.fixture
def analyst_client(analyst_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=analyst_app), base_url="http://test")


@pytest.fixture
def viewer_client(viewer_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=viewer_app), base_url="http://test")


@pytest.fixture
def unauth_client(unauth_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=unauth_app), base_url="http://test")


# ---------------------------------------------------------------------------
# T018: POST /imports/voter-history
# ---------------------------------------------------------------------------


class TestImportVoterHistoryEndpoint:
    """Tests for POST /api/v1/imports/voter-history."""

    @pytest.mark.asyncio
    async def test_returns_202_with_job(self, admin_client: AsyncClient) -> None:
        """Successful upload returns 202 with import job response."""
        mock_job = MagicMock()
        mock_job.id = uuid.uuid4()
        mock_job.file_name = "voter_history.csv"
        mock_job.file_type = "voter_history"
        mock_job.status = "pending"
        mock_job.total_records = None
        mock_job.records_succeeded = None
        mock_job.records_failed = None
        mock_job.records_inserted = None
        mock_job.records_updated = None
        mock_job.records_soft_deleted = None
        mock_job.records_skipped = None
        mock_job.records_unmatched = None
        mock_job.error_log = None
        mock_job.triggered_by = None
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)

        with (
            patch(
                "voter_api.services.import_service.create_import_job",
                new_callable=AsyncMock,
                return_value=mock_job,
            ),
            patch("voter_api.core.background.task_runner.submit_task"),
        ):
            resp = await admin_client.post(
                "/api/v1/imports/voter-history",
                files={"file": ("voter_history.csv", b"header\nrow", "text/csv")},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["file_name"] == "voter_history.csv"
        assert data["file_type"] == "voter_history"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_no_file_returns_422(self, admin_client: AsyncClient) -> None:
        """Missing file returns 422."""
        resp = await admin_client.post("/api/v1/imports/voter-history")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_requires_admin_auth(self, unauth_client: AsyncClient) -> None:
        """Endpoint requires authentication."""
        resp = await unauth_client.post(
            "/api/v1/imports/voter-history",
            files={"file": ("test.csv", b"data", "text/csv")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_forbidden(self, mock_session, mock_viewer_user) -> None:
        """Viewer role cannot access import endpoint."""
        app = FastAPI()
        app.include_router(imports_router, prefix="/api/v1")
        app.dependency_overrides[get_async_session] = lambda: mock_session
        app.dependency_overrides[get_current_user] = lambda: mock_viewer_user
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

        resp = await client.post(
            "/api/v1/imports/voter-history",
            files={"file": ("test.csv", b"data", "text/csv")},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_filename_returns_error(self, admin_client: AsyncClient) -> None:
        """File with no filename returns an error status."""
        resp = await admin_client.post(
            "/api/v1/imports/voter-history",
            files={"file": ("", b"data", "text/csv")},
        )
        # httpx/FastAPI may return 400 or 422 for empty filename
        assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# T025: GET /voters/{reg_num}/history
# ---------------------------------------------------------------------------


class TestGetVoterHistory:
    """Tests for GET /api/v1/voters/{reg_num}/history."""

    @pytest.mark.asyncio
    async def test_returns_history_records(self, analyst_client: AsyncClient) -> None:
        """Returns paginated voter history records."""
        records = [_make_voter_history(), _make_voter_history()]
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=(records, 2),
        ):
            resp = await analyst_client.get("/api/v1/voters/12345678/history")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list(self, analyst_client: AsyncClient) -> None:
        """Voter with no history returns empty list, not 404."""
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await analyst_client.get("/api/v1/voters/00000000/history")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_filter_by_election_type(self, analyst_client: AsyncClient) -> None:
        """election_type query param is passed to service."""
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            await analyst_client.get("/api/v1/voters/12345678/history?election_type=GENERAL ELECTION")

        mock_svc.assert_awaited_once()
        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["election_type"] == "GENERAL ELECTION"

    @pytest.mark.asyncio
    async def test_date_range_filtering(self, analyst_client: AsyncClient) -> None:
        """date_from and date_to query params are passed to service."""
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            await analyst_client.get("/api/v1/voters/12345678/history?date_from=2024-01-01&date_to=2024-12-31")

        mock_svc.assert_awaited_once()
        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["date_from"] == date(2024, 1, 1)
        assert call_kwargs[1]["date_to"] == date(2024, 12, 31)

    @pytest.mark.asyncio
    async def test_pagination(self, analyst_client: AsyncClient) -> None:
        """Page and page_size are forwarded to service."""
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            await analyst_client.get("/api/v1/voters/12345678/history?page=3&page_size=10")

        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["page"] == 3
        assert call_kwargs[1]["page_size"] == 10

    @pytest.mark.asyncio
    async def test_admin_allowed(self, admin_client: AsyncClient) -> None:
        """Admin role can access voter history."""
        with patch(
            "voter_api.services.voter_history_service.get_voter_history",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await admin_client.get("/api/v1/voters/12345678/history")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_viewer_forbidden(self, viewer_client: AsyncClient) -> None:
        """Viewer role gets 403 for voter history."""
        resp = await viewer_client.get("/api/v1/voters/12345678/history")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, unauth_client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        resp = await unauth_client.get("/api/v1/voters/12345678/history")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# T026: Voter detail enrichment
# ---------------------------------------------------------------------------


class TestVoterDetailEnrichment:
    """Tests for participation_summary in voter detail response.

    These verify the ParticipationSummary schema independently since
    the voter detail endpoint integration requires a full database setup.
    """

    def test_summary_with_data(self) -> None:
        """ParticipationSummary with populated values."""
        summary = ParticipationSummary(
            total_elections=5,
            last_election_date=date(2024, 11, 5),
        )
        assert summary.total_elections == 5
        assert summary.last_election_date == date(2024, 11, 5)

    def test_summary_defaults(self) -> None:
        """Default ParticipationSummary is zero/null."""
        summary = ParticipationSummary()
        assert summary.total_elections == 0
        assert summary.last_election_date is None

    def test_summary_serializes(self) -> None:
        """Summary serializes to JSON-compatible dict."""
        summary = ParticipationSummary(total_elections=3, last_election_date=date(2024, 5, 21))
        data = summary.model_dump(mode="json")
        assert data["total_elections"] == 3
        assert data["last_election_date"] == "2024-05-21"


# ---------------------------------------------------------------------------
# T036: GET /elections/{id}/participation
# ---------------------------------------------------------------------------


class TestListElectionParticipants:
    """Tests for GET /api/v1/elections/{id}/participation."""

    @pytest.mark.asyncio
    async def test_returns_participants(self, analyst_client: AsyncClient) -> None:
        """Returns paginated list of participants."""
        records = [_make_voter_history(), _make_voter_history()]
        with patch(
            "voter_api.services.voter_history_service.list_election_participants",
            new_callable=AsyncMock,
            return_value=(records, 2),
        ):
            eid = uuid.uuid4()
            resp = await analyst_client.get(f"/api/v1/elections/{eid}/participation")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 2

    @pytest.mark.asyncio
    async def test_404_for_unknown_election(self, analyst_client: AsyncClient) -> None:
        """Returns 404 when election does not exist."""
        with patch(
            "voter_api.services.voter_history_service.list_election_participants",
            new_callable=AsyncMock,
            side_effect=ValueError("Election not found"),
        ):
            eid = uuid.uuid4()
            resp = await analyst_client.get(f"/api/v1/elections/{eid}/participation")

        assert resp.status_code == 404
        assert "Election not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_filter_by_county(self, analyst_client: AsyncClient) -> None:
        """County filter is forwarded to service."""
        with patch(
            "voter_api.services.voter_history_service.list_election_participants",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            eid = uuid.uuid4()
            await analyst_client.get(f"/api/v1/elections/{eid}/participation?county=FULTON")

        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["county"] == "FULTON"

    @pytest.mark.asyncio
    async def test_filter_by_absentee(self, analyst_client: AsyncClient) -> None:
        """Boolean absentee filter is forwarded."""
        with patch(
            "voter_api.services.voter_history_service.list_election_participants",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            eid = uuid.uuid4()
            await analyst_client.get(f"/api/v1/elections/{eid}/participation?absentee=true")

        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["absentee"] is True

    @pytest.mark.asyncio
    async def test_pagination(self, analyst_client: AsyncClient) -> None:
        """Pagination params are forwarded."""
        with patch(
            "voter_api.services.voter_history_service.list_election_participants",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_svc:
            eid = uuid.uuid4()
            await analyst_client.get(f"/api/v1/elections/{eid}/participation?page=2&page_size=50")

        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["page"] == 2
        assert call_kwargs[1]["page_size"] == 50

    @pytest.mark.asyncio
    async def test_viewer_forbidden(self, viewer_client: AsyncClient) -> None:
        """Viewer role gets 403."""
        eid = uuid.uuid4()
        resp = await viewer_client.get(f"/api/v1/elections/{eid}/participation")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, unauth_client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        eid = uuid.uuid4()
        resp = await unauth_client.get(f"/api/v1/elections/{eid}/participation")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# T037: GET /elections/{id}/participation/stats
# ---------------------------------------------------------------------------


class TestGetParticipationStats:
    """Tests for GET /api/v1/elections/{id}/participation/stats."""

    @pytest.mark.asyncio
    async def test_returns_stats(self, analyst_client: AsyncClient) -> None:
        """Returns participation stats with breakdowns."""
        eid = uuid.uuid4()
        stats = ParticipationStatsResponse(
            election_id=eid,
            total_participants=200,
            by_county=[
                CountyBreakdown(county="FULTON", count=120),
                CountyBreakdown(county="DEKALB", count=80),
            ],
            by_ballot_style=[
                BallotStyleBreakdown(ballot_style="STD", count=200),
            ],
        )
        with patch(
            "voter_api.services.voter_history_service.get_participation_stats",
            new_callable=AsyncMock,
            return_value=stats,
        ):
            resp = await analyst_client.get(f"/api/v1/elections/{eid}/participation/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_participants"] == 200
        assert len(data["by_county"]) == 2
        assert data["by_county"][0]["county"] == "FULTON"
        assert data["by_county"][0]["count"] == 120
        assert len(data["by_ballot_style"]) == 1

    @pytest.mark.asyncio
    async def test_404_for_unknown_election(self, analyst_client: AsyncClient) -> None:
        """Returns 404 when election does not exist."""
        with patch(
            "voter_api.services.voter_history_service.get_participation_stats",
            new_callable=AsyncMock,
            side_effect=ValueError("Election not found"),
        ):
            eid = uuid.uuid4()
            resp = await analyst_client.get(f"/api/v1/elections/{eid}/participation/stats")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_allowed(self, viewer_client: AsyncClient) -> None:
        """Viewer role CAN access stats (all authenticated users)."""
        eid = uuid.uuid4()
        stats = ParticipationStatsResponse(
            election_id=eid,
            total_participants=0,
        )
        with patch(
            "voter_api.services.voter_history_service.get_participation_stats",
            new_callable=AsyncMock,
            return_value=stats,
        ):
            resp = await viewer_client.get(f"/api/v1/elections/{eid}/participation/stats")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, unauth_client: AsyncClient) -> None:
        """Unauthenticated request returns 401."""
        eid = uuid.uuid4()
        resp = await unauth_client.get(f"/api/v1/elections/{eid}/participation/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_stats(self, analyst_client: AsyncClient) -> None:
        """Election with no participants returns zero counts."""
        eid = uuid.uuid4()
        stats = ParticipationStatsResponse(
            election_id=eid,
            total_participants=0,
            by_county=[],
            by_ballot_style=[],
        )
        with patch(
            "voter_api.services.voter_history_service.get_participation_stats",
            new_callable=AsyncMock,
            return_value=stats,
        ):
            resp = await analyst_client.get(f"/api/v1/elections/{eid}/participation/stats")

        data = resp.json()
        assert data["total_participants"] == 0
        assert data["by_county"] == []
        assert data["by_ballot_style"] == []
