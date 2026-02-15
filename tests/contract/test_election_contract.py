"""Contract tests validating election tracking Pydantic schemas match OpenAPI spec.

Verifies all election response schemas can be instantiated with expected fields
and produce valid JSON-serializable output matching contracts/openapi.yaml.
"""

import uuid
from datetime import UTC, date, datetime

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.election import (
    CandidateResult,
    CountyResultSummary,
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionResultFeature,
    ElectionResultFeatureCollection,
    ElectionResultsResponse,
    ElectionSummary,
    ElectionUpdateRequest,
    PaginatedElectionListResponse,
    RefreshResponse,
    VoteMethodResult,
)


class TestElectionCreateRequest:
    def test_valid_request(self):
        req = ElectionCreateRequest(
            name="General Election 2024",
            election_date=date(2024, 11, 5),
            election_type="general",
            district="Georgia Statewide",
            data_source_url="https://sos.ga.gov/results.json",
        )
        data = req.model_dump()
        assert data["name"] == "General Election 2024"
        assert data["election_type"] == "general"
        assert data["refresh_interval_seconds"] == 120  # default

    def test_custom_refresh_interval(self):
        req = ElectionCreateRequest(
            name="Fast Refresh",
            election_date=date(2024, 11, 5),
            election_type="special",
            district="District 18",
            data_source_url="https://example.com/feed.json",
            refresh_interval_seconds=300,
        )
        assert req.refresh_interval_seconds == 300


class TestElectionUpdateRequest:
    def test_partial_update(self):
        req = ElectionUpdateRequest(status="finalized")
        data = req.model_dump(exclude_unset=True)
        assert data == {"status": "finalized"}
        assert "name" not in data

    def test_all_fields(self):
        req = ElectionUpdateRequest(
            name="Updated Name",
            data_source_url="https://new-url.com/feed.json",
            status="finalized",
            refresh_interval_seconds=600,
        )
        data = req.model_dump(exclude_unset=True)
        assert len(data) == 4


class TestElectionSummary:
    def test_required_fields(self):
        summary = ElectionSummary(
            id=uuid.uuid4(),
            name="Test Election",
            election_date=date(2024, 11, 5),
            election_type="general",
            district="Statewide",
            status="active",
            last_refreshed_at=None,
            precincts_reporting=None,
            precincts_participating=None,
        )
        data = summary.model_dump(mode="json")
        assert "id" in data
        assert "name" in data
        assert "election_date" in data
        assert "election_type" in data
        assert "district" in data
        assert "status" in data
        assert "last_refreshed_at" in data
        assert data["precincts_reporting"] is None

    def test_with_precinct_data(self):
        summary = ElectionSummary(
            id=uuid.uuid4(),
            name="Test",
            election_date=date(2024, 11, 5),
            election_type="general",
            district="Statewide",
            status="active",
            last_refreshed_at=datetime(2024, 11, 5, 18, 30, tzinfo=UTC),
            precincts_reporting=2450,
            precincts_participating=2600,
        )
        data = summary.model_dump(mode="json")
        assert data["precincts_reporting"] == 2450
        assert data["precincts_participating"] == 2600


class TestElectionDetailResponse:
    def test_includes_extra_fields(self):
        detail = ElectionDetailResponse(
            id=uuid.uuid4(),
            name="Test",
            election_date=date(2024, 11, 5),
            election_type="general",
            district="Statewide",
            status="active",
            last_refreshed_at=None,
            data_source_url="https://example.com/feed.json",
            refresh_interval_seconds=120,
            created_at=datetime(2024, 10, 1, tzinfo=UTC),
            updated_at=datetime(2024, 11, 5, tzinfo=UTC),
        )
        data = detail.model_dump(mode="json")
        assert "data_source_url" in data
        assert "refresh_interval_seconds" in data
        assert "created_at" in data
        assert "updated_at" in data


class TestPaginatedElectionListResponse:
    def test_structure(self):
        resp = PaginatedElectionListResponse(
            items=[
                ElectionSummary(
                    id=uuid.uuid4(),
                    name="Test",
                    election_date=date(2024, 11, 5),
                    election_type="general",
                    district="Statewide",
                    status="active",
                    last_refreshed_at=None,
                ),
            ],
            pagination=PaginationMeta(total=1, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data
        assert len(data["items"]) == 1
        assert data["pagination"]["total"] == 1


class TestVoteMethodResult:
    def test_fields(self):
        vmr = VoteMethodResult(group_name="Election Day", vote_count=800)
        data = vmr.model_dump()
        assert data["group_name"] == "Election Day"
        assert data["vote_count"] == 800


class TestCandidateResult:
    def test_all_fields(self):
        cr = CandidateResult(
            id="2",
            name="Jane Smith",
            political_party="Democratic",
            ballot_order=1,
            vote_count=1234567,
            group_results=[
                VoteMethodResult(group_name="Advance Voting", vote_count=45000),
            ],
        )
        data = cr.model_dump()
        assert data["id"] == "2"
        assert data["name"] == "Jane Smith"
        assert data["political_party"] == "Democratic"
        assert len(data["group_results"]) == 1


class TestCountyResultSummary:
    def test_fields(self):
        crs = CountyResultSummary(
            county_name="Fulton County",
            precincts_participating=245,
            precincts_reporting=200,
            candidates=[
                CandidateResult(
                    id="1",
                    name="Candidate",
                    political_party="Dem",
                    ballot_order=1,
                    vote_count=100,
                ),
            ],
        )
        data = crs.model_dump()
        assert data["county_name"] == "Fulton County"
        assert len(data["candidates"]) == 1


class TestElectionResultsResponse:
    def test_full_structure(self):
        resp = ElectionResultsResponse(
            election_id=uuid.uuid4(),
            election_name="General Election 2024",
            election_date=date(2024, 11, 5),
            status="active",
            last_refreshed_at=datetime(2024, 11, 5, 18, 30, tzinfo=UTC),
            precincts_participating=2600,
            precincts_reporting=2450,
            candidates=[
                CandidateResult(
                    id="2",
                    name="Jane Smith",
                    political_party="Dem",
                    ballot_order=1,
                    vote_count=1234567,
                ),
            ],
            county_results=[
                CountyResultSummary(
                    county_name="Fulton County",
                    precincts_participating=245,
                    precincts_reporting=200,
                    candidates=[],
                ),
            ],
        )
        data = resp.model_dump(mode="json")
        assert "election_id" in data
        assert "election_name" in data
        assert "candidates" in data
        assert "county_results" in data
        assert data["status"] == "active"


class TestElectionResultFeature:
    def test_geojson_feature(self):
        feature = ElectionResultFeature(
            geometry={
                "type": "Polygon",
                "coordinates": [[[-84.5, 33.5], [-84.5, 33.8], [-84.2, 33.8], [-84.2, 33.5], [-84.5, 33.5]]],
            },
            properties={
                "county_name": "Fulton County",
                "precincts_reporting": 200,
                "precincts_participating": 245,
                "candidates": [],
            },
        )
        data = feature.model_dump()
        assert data["type"] == "Feature"
        assert data["geometry"]["type"] == "Polygon"

    def test_null_geometry(self):
        feature = ElectionResultFeature(
            geometry=None,
            properties={
                "county_name": "Unknown",
                "precincts_reporting": None,
                "precincts_participating": None,
                "candidates": [],
            },
        )
        data = feature.model_dump()
        assert data["geometry"] is None


class TestElectionResultFeatureCollection:
    def test_structure(self):
        fc = ElectionResultFeatureCollection(
            election_id=uuid.uuid4(),
            election_name="Test",
            election_date=date(2024, 11, 5),
            status="active",
            last_refreshed_at=datetime(2024, 11, 5, 18, 30, tzinfo=UTC),
            features=[],
        )
        data = fc.model_dump(mode="json")
        assert data["type"] == "FeatureCollection"
        assert "election_id" in data
        assert "election_name" in data
        assert "election_date" in data
        assert "status" in data
        assert "last_refreshed_at" in data
        assert "features" in data


class TestRefreshResponse:
    def test_all_fields(self):
        resp = RefreshResponse(
            election_id=uuid.uuid4(),
            refreshed_at=datetime(2024, 11, 5, 18, 45, 30, tzinfo=UTC),
            precincts_reporting=2500,
            precincts_participating=2600,
            counties_updated=25,
        )
        data = resp.model_dump(mode="json")
        assert "election_id" in data
        assert "refreshed_at" in data
        assert data["precincts_reporting"] == 2500
        assert data["counties_updated"] == 25

    def test_nullable_precincts(self):
        resp = RefreshResponse(
            election_id=uuid.uuid4(),
            refreshed_at=datetime.now(UTC),
            precincts_reporting=None,
            precincts_participating=None,
            counties_updated=0,
        )
        data = resp.model_dump()
        assert data["precincts_reporting"] is None
        assert data["precincts_participating"] is None
