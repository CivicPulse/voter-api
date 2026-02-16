"""Integration tests for election tracking API endpoints."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elections import elections_router
from voter_api.core.dependencies import get_async_session, get_current_user
from voter_api.models.election import Election, ElectionCountyResult, ElectionResult


def _make_election(**overrides) -> Election:
    """Build a mock Election model instance."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test Election",
        "election_date": date(2026, 2, 17),
        "election_type": "special",
        "district": "State Senate - District 18",
        "data_source_url": "https://example.com/feed.json",
        "status": "active",
        "last_refreshed_at": datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
        "refresh_interval_seconds": 120,
        "created_at": datetime(2026, 2, 14, 10, 0, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 2, 14, 10, 0, 0, tzinfo=UTC),
        "ballot_item_id": None,
        "result": None,
        "county_results": [],
    }
    defaults.update(overrides)
    election = MagicMock(spec=Election)
    for k, v in defaults.items():
        setattr(election, k, v)
    return election


def _make_result(election_id: uuid.UUID, **overrides) -> ElectionResult:
    """Build a mock ElectionResult model instance."""
    defaults = {
        "id": uuid.uuid4(),
        "election_id": election_id,
        "precincts_participating": 100,
        "precincts_reporting": 95,
        "results_data": [
            {
                "id": "2",
                "name": "Jane Doe (Dem)",
                "ballotOrder": 1,
                "voteCount": 1234,
                "politicalParty": "Dem",
                "groupResults": [
                    {"groupName": "Election Day", "voteCount": 800},
                    {"groupName": "Advance Voting", "voteCount": 434},
                ],
            },
            {
                "id": "4",
                "name": "John Smith (Rep)",
                "ballotOrder": 2,
                "voteCount": 5678,
                "politicalParty": "Rep",
                "groupResults": [
                    {"groupName": "Election Day", "voteCount": 3000},
                    {"groupName": "Advance Voting", "voteCount": 2678},
                ],
            },
        ],
        "source_created_at": datetime(2026, 2, 17, 11, 0, 0, tzinfo=UTC),
        "fetched_at": datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    result = MagicMock(spec=ElectionResult)
    for k, v in defaults.items():
        setattr(result, k, v)
    return result


def _make_county_result(election_id: uuid.UUID, county_name: str = "Houston County") -> ElectionCountyResult:
    """Build a mock ElectionCountyResult."""
    cr = MagicMock(spec=ElectionCountyResult)
    cr.id = uuid.uuid4()
    cr.election_id = election_id
    cr.county_name = county_name
    cr.county_name_normalized = county_name.removesuffix(" County")
    cr.precincts_participating = 7
    cr.precincts_reporting = 5
    cr.results_data = [
        {
            "id": "2",
            "name": "Jane Doe (Dem)",
            "ballotOrder": 1,
            "voteCount": 42,
            "politicalParty": "Dem",
            "groupResults": [],
        },
    ]
    return cr


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
    """Minimal FastAPI app with elections router (no auth by default)."""
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    return app


@pytest.fixture
def admin_app(mock_session, mock_admin_user) -> FastAPI:
    """FastAPI app with admin auth."""
    app = FastAPI()
    app.include_router(elections_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    return app


@pytest.fixture
def client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def admin_client(admin_app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=admin_app), base_url="http://test")


# --- US1: GET /elections/{id} ---


class TestGetElection:
    @pytest.mark.asyncio
    async def test_get_election_returns_detail(self, client):
        election = _make_election()
        result = _make_result(election.id)
        election.result = result

        with patch("voter_api.services.election_service.get_election_by_id", return_value=election):
            resp = await client.get(f"/api/v1/elections/{election.id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Election"
        assert data["election_type"] == "special"
        assert data["district"] == "State Senate - District 18"
        assert data["precincts_reporting"] == 95
        assert data["precincts_participating"] == 100

    @pytest.mark.asyncio
    async def test_get_election_404(self, client):
        fake_id = uuid.uuid4()
        with patch("voter_api.services.election_service.get_election_by_id", return_value=None):
            resp = await client.get(f"/api/v1/elections/{fake_id}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Election not found."


# --- US1: GET /elections/{id}/results ---


class TestGetElectionResults:
    @pytest.mark.asyncio
    async def test_returns_results_with_candidates(self, client):
        from voter_api.schemas.election import (
            CandidateResult,
            ElectionResultsResponse,
            VoteMethodResult,
        )

        mock_response = ElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
            precincts_participating=100,
            precincts_reporting=95,
            candidates=[
                CandidateResult(
                    id="2",
                    name="Jane Doe",
                    political_party="Dem",
                    ballot_order=1,
                    vote_count=1234,
                    group_results=[VoteMethodResult(group_name="Election Day", vote_count=800)],
                ),
            ],
            county_results=[],
        )

        with patch("voter_api.services.election_service.get_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["name"] == "Jane Doe"
        assert data["precincts_reporting"] == 95

    @pytest.mark.asyncio
    async def test_cache_control_active_election(self, client):
        from voter_api.schemas.election import ElectionResultsResponse

        mock_response = ElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            candidates=[],
            county_results=[],
        )

        with patch("voter_api.services.election_service.get_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results")

        assert resp.headers["cache-control"] == "public, max-age=60"

    @pytest.mark.asyncio
    async def test_cache_control_finalized_election(self, client):
        from voter_api.schemas.election import ElectionResultsResponse

        mock_response = ElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="finalized",
            last_refreshed_at=None,
            candidates=[],
            county_results=[],
        )

        with patch("voter_api.services.election_service.get_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results")

        assert resp.headers["cache-control"] == "public, max-age=86400"

    @pytest.mark.asyncio
    async def test_results_404(self, client):
        with patch("voter_api.services.election_service.get_election_results", return_value=None):
            resp = await client.get(f"/api/v1/elections/{uuid.uuid4()}/results")
        assert resp.status_code == 404


# --- FR-006: GET /elections/{id}/results/raw ---


class TestGetRawElectionResults:
    @pytest.mark.asyncio
    async def test_returns_raw_results(self, client):
        from voter_api.schemas.election import RawCountyResult, RawElectionResultsResponse

        mock_response = RawElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=datetime(2026, 2, 17, 12, 0, 0, tzinfo=UTC),
            source_created_at=datetime(2026, 2, 9, 17, 40, 56, tzinfo=UTC),
            precincts_participating=100,
            precincts_reporting=95,
            statewide_results=[
                {
                    "id": "2",
                    "name": "Jane Doe (Dem)",
                    "ballotOrder": 1,
                    "voteCount": 1234,
                    "politicalParty": "Dem",
                    "groupResults": [{"groupName": "Election Day", "voteCount": 800}],
                },
            ],
            county_results=[
                RawCountyResult(
                    county_name="Houston County",
                    precincts_participating=7,
                    precincts_reporting=5,
                    results=[
                        {
                            "id": "2",
                            "name": "Jane Doe (Dem)",
                            "voteCount": 42,
                            "politicalParty": "Dem",
                        },
                    ],
                ),
            ],
        )

        with patch("voter_api.services.election_service.get_raw_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results/raw")

        assert resp.status_code == 200
        data = resp.json()
        assert data["source_created_at"] is not None
        # camelCase keys preserved in raw results
        assert data["statewide_results"][0]["politicalParty"] == "Dem"
        assert data["statewide_results"][0]["voteCount"] == 1234
        assert data["county_results"][0]["county_name"] == "Houston County"
        assert data["county_results"][0]["results"][0]["politicalParty"] == "Dem"

    @pytest.mark.asyncio
    async def test_cache_control_active(self, client):
        from voter_api.schemas.election import RawElectionResultsResponse

        mock_response = RawElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            statewide_results=[],
            county_results=[],
        )

        with patch("voter_api.services.election_service.get_raw_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results/raw")

        assert resp.headers["cache-control"] == "public, max-age=60"

    @pytest.mark.asyncio
    async def test_cache_control_finalized(self, client):
        from voter_api.schemas.election import RawElectionResultsResponse

        mock_response = RawElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="finalized",
            last_refreshed_at=None,
            statewide_results=[],
            county_results=[],
        )

        with patch("voter_api.services.election_service.get_raw_election_results", return_value=mock_response):
            resp = await client.get(f"/api/v1/elections/{mock_response.election_id}/results/raw")

        assert resp.headers["cache-control"] == "public, max-age=86400"

    @pytest.mark.asyncio
    async def test_raw_results_404(self, client):
        with patch("voter_api.services.election_service.get_raw_election_results", return_value=None):
            resp = await client.get(f"/api/v1/elections/{uuid.uuid4()}/results/raw")
        assert resp.status_code == 404


# --- US4: POST /elections ---


class TestCreateElection:
    @pytest.mark.asyncio
    async def test_create_returns_201(self, admin_client):
        election = _make_election()
        with patch("voter_api.services.election_service.create_election", return_value=election):
            resp = await admin_client.post(
                "/api/v1/elections",
                json={
                    "name": "Test Election",
                    "election_date": "2026-02-17",
                    "election_type": "special",
                    "district": "State Senate - District 18",
                    "data_source_url": "https://example.com/feed.json",
                },
            )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Test Election"

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_409(self, admin_client):
        from voter_api.services.election_service import DuplicateElectionError

        with patch(
            "voter_api.services.election_service.create_election",
            side_effect=DuplicateElectionError("already exists"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections",
                json={
                    "name": "Test Election",
                    "election_date": "2026-02-17",
                    "election_type": "special",
                    "district": "State Senate - District 18",
                    "data_source_url": "https://example.com/feed.json",
                },
            )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_requires_auth(self, client):
        resp = await client.post(
            "/api/v1/elections",
            json={
                "name": "Test",
                "election_date": "2026-02-17",
                "election_type": "special",
                "district": "District 18",
                "data_source_url": "https://example.com/feed.json",
            },
        )
        assert resp.status_code == 401


# --- US4: PATCH /elections/{id} ---


class TestUpdateElection:
    @pytest.mark.asyncio
    async def test_update_returns_updated(self, admin_client):
        election = _make_election(status="finalized")
        with patch("voter_api.services.election_service.update_election", return_value=election):
            resp = await admin_client.patch(
                f"/api/v1/elections/{election.id}",
                json={"status": "finalized"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "finalized"

    @pytest.mark.asyncio
    async def test_update_404(self, admin_client):
        with patch("voter_api.services.election_service.update_election", return_value=None):
            resp = await admin_client.patch(
                f"/api/v1/elections/{uuid.uuid4()}",
                json={"status": "finalized"},
            )
        assert resp.status_code == 404


# --- US4: POST /elections/{id}/refresh ---


class TestRefreshElection:
    @pytest.mark.asyncio
    async def test_refresh_returns_response(self, admin_client):
        from voter_api.schemas.election import RefreshResponse

        mock_resp = RefreshResponse(
            election_id=uuid.uuid4(),
            refreshed_at=datetime.now(UTC),
            precincts_reporting=95,
            precincts_participating=100,
            counties_updated=5,
        )
        with patch("voter_api.services.election_service.refresh_single_election", return_value=mock_resp):
            resp = await admin_client.post(f"/api/v1/elections/{mock_resp.election_id}/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["counties_updated"] == 5

    @pytest.mark.asyncio
    async def test_refresh_404(self, admin_client):
        with patch(
            "voter_api.services.election_service.refresh_single_election",
            side_effect=ValueError("Election not found."),
        ):
            resp = await admin_client.post(f"/api/v1/elections/{uuid.uuid4()}/refresh")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_refresh_502_on_fetch_error(self, admin_client):
        from voter_api.lib.election_tracker import FetchError

        with patch(
            "voter_api.services.election_service.refresh_single_election",
            side_effect=FetchError("Connection failed"),
        ):
            resp = await admin_client.post(f"/api/v1/elections/{uuid.uuid4()}/refresh")
        assert resp.status_code == 502
        assert "retry" in resp.json()["detail"].lower()


# --- US5: GET /elections ---


class TestListElections:
    @pytest.mark.asyncio
    async def test_list_returns_paginated(self, client):
        from voter_api.schemas.election import ElectionSummary

        items = [
            ElectionSummary(
                id=uuid.uuid4(),
                name="Election 1",
                election_date=date(2026, 2, 17),
                election_type="special",
                district="District 18",
                status="active",
                last_refreshed_at=None,
            ),
        ]
        with patch("voter_api.services.election_service.list_elections", return_value=(items, 1)):
            resp = await client.get("/api/v1/elections")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["pagination"]["total"] == 1
        assert data["pagination"]["page"] == 1

    @pytest.mark.asyncio
    async def test_list_with_filters(self, client):
        with patch("voter_api.services.election_service.list_elections", return_value=([], 0)) as mock_list:
            resp = await client.get("/api/v1/elections?status=active&election_type=special&page=2&page_size=10")

        assert resp.status_code == 200
        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args[1]
        assert call_kwargs["status"] == "active"
        assert call_kwargs["election_type"] == "special"
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 10


# --- US2: GET /elections/{id}/results/geojson ---


class TestGetElectionResultsGeoJSON:
    @pytest.mark.asyncio
    async def test_returns_geojson_feature_collection(self, client):
        from voter_api.schemas.election import (
            ElectionResultFeature,
            ElectionResultFeatureCollection,
        )

        election = _make_election()
        mock_fc = ElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            features=[
                ElectionResultFeature(
                    geometry={
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-84.5, 33.5],
                                [-84.5, 33.8],
                                [-84.2, 33.8],
                                [-84.2, 33.5],
                                [-84.5, 33.5],
                            ]
                        ],
                    },
                    properties={
                        "county_name": "Houston County",
                        "precincts_reporting": 5,
                        "precincts_participating": 7,
                        "candidates": [],
                    },
                ),
            ],
        )

        with (
            patch("voter_api.services.election_service.get_election_results_geojson", return_value=mock_fc),
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/geo+json"
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        assert data["features"][0]["type"] == "Feature"
        assert data["election_id"] == str(election.id)

    @pytest.mark.asyncio
    async def test_geojson_cache_control(self, client):
        from voter_api.schemas.election import ElectionResultFeatureCollection

        election = _make_election(status="finalized")
        mock_fc = ElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="finalized",
            last_refreshed_at=None,
            features=[],
        )

        with (
            patch("voter_api.services.election_service.get_election_results_geojson", return_value=mock_fc),
            patch("voter_api.services.election_service.get_election_by_id", return_value=election),
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson")

        assert resp.headers["cache-control"] == "public, max-age=86400"

    @pytest.mark.asyncio
    async def test_geojson_404(self, client):
        with patch("voter_api.services.election_service.get_election_results_geojson", return_value=None):
            resp = await client.get(f"/api/v1/elections/{uuid.uuid4()}/results/geojson")
        assert resp.status_code == 404


# --- US2b: GET /elections/{id}/results/geojson/precincts ---


class TestGetElectionResultsGeoJSONPrecincts:
    @pytest.mark.asyncio
    async def test_returns_precinct_geojson(self, client):
        from voter_api.schemas.election import (
            PrecinctElectionResultFeature,
            PrecinctElectionResultFeatureCollection,
        )

        election = _make_election()
        mock_fc = PrecinctElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            features=[
                PrecinctElectionResultFeature(
                    geometry={
                        "type": "MultiPolygon",
                        "coordinates": [[[[-84.5, 33.5], [-84.5, 33.8], [-84.2, 33.8], [-84.5, 33.5]]]],
                    },
                    properties={
                        "precinct_id": "ANNX",
                        "precinct_name": "Annex",
                        "county": "Houston County",
                        "reporting_status": "Reported",
                        "candidates": [],
                    },
                ),
            ],
        )

        with patch(
            "voter_api.services.election_service.get_election_precinct_results_geojson",
            return_value=mock_fc,
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson/precincts")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/geo+json"
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1
        assert data["features"][0]["properties"]["precinct_id"] == "ANNX"

    @pytest.mark.asyncio
    async def test_county_filter_passed(self, client):
        from voter_api.schemas.election import PrecinctElectionResultFeatureCollection

        election = _make_election()
        mock_fc = PrecinctElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            features=[],
        )

        with patch(
            "voter_api.services.election_service.get_election_precinct_results_geojson",
            return_value=mock_fc,
        ) as mock_svc:
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson/precincts?county=Houston")

        assert resp.status_code == 200
        mock_svc.assert_awaited_once()
        call_kwargs = mock_svc.call_args
        assert call_kwargs[1]["county"] == "Houston" or call_kwargs[0][2] == "Houston"

    @pytest.mark.asyncio
    async def test_cache_control_active(self, client):
        from voter_api.schemas.election import PrecinctElectionResultFeatureCollection

        election = _make_election(status="active")
        mock_fc = PrecinctElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="active",
            last_refreshed_at=None,
            features=[],
        )

        with patch(
            "voter_api.services.election_service.get_election_precinct_results_geojson",
            return_value=mock_fc,
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson/precincts")

        assert resp.headers["cache-control"] == "public, max-age=60"

    @pytest.mark.asyncio
    async def test_cache_control_finalized(self, client):
        from voter_api.schemas.election import PrecinctElectionResultFeatureCollection

        election = _make_election(status="finalized")
        mock_fc = PrecinctElectionResultFeatureCollection(
            election_id=election.id,
            election_name="Test",
            election_date=date(2026, 2, 17),
            status="finalized",
            last_refreshed_at=None,
            features=[],
        )

        with patch(
            "voter_api.services.election_service.get_election_precinct_results_geojson",
            return_value=mock_fc,
        ):
            resp = await client.get(f"/api/v1/elections/{election.id}/results/geojson/precincts")

        assert resp.headers["cache-control"] == "public, max-age=86400"

    @pytest.mark.asyncio
    async def test_precinct_geojson_404(self, client):
        with patch(
            "voter_api.services.election_service.get_election_precinct_results_geojson",
            return_value=None,
        ):
            resp = await client.get(f"/api/v1/elections/{uuid.uuid4()}/results/geojson/precincts")
        assert resp.status_code == 404


# --- Feed import preview ---


_FEED_IMPORT_BODY = {
    "data_source_url": "https://results.sos.ga.gov/feed.json",
    "election_type": "general",
}


class TestPreviewFeedImport:
    @pytest.mark.asyncio
    async def test_preview_returns_races(self, admin_client):
        from voter_api.schemas.election import FeedImportPreviewResponse, FeedRaceSummary

        mock_preview = FeedImportPreviewResponse(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_date=date(2025, 11, 4),
            election_name="Test Election",
            detected_election_type="general",
            races=[
                FeedRaceSummary(ballot_item_id="S10", name="PSC - District 2", candidate_count=2),
                FeedRaceSummary(ballot_item_id="S11", name="PSC - District 3", candidate_count=1),
            ],
        )

        with patch(
            "voter_api.services.election_service.preview_feed_import",
            new_callable=AsyncMock,
            return_value=mock_preview,
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed/preview",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_races"] == 2
        assert data["races"][0]["ballot_item_id"] == "S10"

    @pytest.mark.asyncio
    async def test_preview_requires_auth(self, client):
        resp = await client.post(
            "/api/v1/elections/import-feed/preview",
            json=_FEED_IMPORT_BODY,
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_preview_fetch_error_returns_502(self, admin_client):
        from voter_api.lib.election_tracker import FetchError

        with patch(
            "voter_api.services.election_service.preview_feed_import",
            new_callable=AsyncMock,
            side_effect=FetchError("connection failed"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed/preview",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_preview_value_error_returns_422(self, admin_client):
        with patch(
            "voter_api.services.election_service.preview_feed_import",
            new_callable=AsyncMock,
            side_effect=ValueError("invalid date"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed/preview",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 422


# --- Feed import ---


class TestImportFeed:
    @pytest.mark.asyncio
    async def test_import_creates_elections(self, admin_client):
        from voter_api.schemas.election import FeedImportedElection, FeedImportResponse

        mock_response = FeedImportResponse(
            elections=[
                FeedImportedElection(
                    election_id=uuid.uuid4(),
                    ballot_item_id="S10",
                    name="Test - PSC District 2",
                    election_date=date(2025, 11, 4),
                    status="active",
                    refreshed=False,
                ),
            ],
        )

        with patch(
            "voter_api.services.election_service.import_feed",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["elections_created"] == 1
        assert data["elections"][0]["ballot_item_id"] == "S10"

    @pytest.mark.asyncio
    async def test_import_requires_auth(self, client):
        resp = await client.post(
            "/api/v1/elections/import-feed",
            json=_FEED_IMPORT_BODY,
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_import_empty_feed_returns_400(self, admin_client):
        with patch(
            "voter_api.services.election_service.import_feed",
            new_callable=AsyncMock,
            side_effect=ValueError("Feed contains no ballot items"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_import_fetch_error_returns_502(self, admin_client):
        from voter_api.lib.election_tracker import FetchError

        with patch(
            "voter_api.services.election_service.import_feed",
            new_callable=AsyncMock,
            side_effect=FetchError("connection failed"),
        ):
            resp = await admin_client.post(
                "/api/v1/elections/import-feed",
                json=_FEED_IMPORT_BODY,
            )

        assert resp.status_code == 502
