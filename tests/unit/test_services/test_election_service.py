"""Unit tests for the election service module."""

import asyncio
import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.lib.election_tracker.ingester import (
    CountyResultData,
    IngestionResult,
    StatewideResultData,
)
from voter_api.schemas.election import (
    CandidateResult,
    ElectionCreateRequest,
    ElectionDetailResponse,
    ElectionResultsResponse,
    ElectionSummary,
    PrecinctCandidateResult,
    PrecinctElectionResultFeatureCollection,
    RawElectionResultsResponse,
    RefreshResponse,
    VoteMethodResult,
)
from voter_api.services.election_service import (
    DuplicateElectionError,
    _ballot_option_to_candidate,
    _persist_ingestion_result,
    _transpose_precinct_results,
    build_detail_response,
    create_election,
    election_refresh_loop,
    get_election_by_id,
    get_election_precinct_results_geojson,
    get_election_results,
    get_raw_election_results,
    list_elections,
    refresh_all_active_elections,
    refresh_single_election,
    update_election,
)

# --- Helpers ---


def _mock_election(**overrides: object) -> MagicMock:
    """Create a mock Election ORM instance."""
    election = MagicMock()
    election.id = uuid.uuid4()
    election.name = "GA Senate District 18 Special"
    election.election_date = date(2026, 2, 17)
    election.election_type = "special"
    election.district = "State Senate - District 18"
    election.status = "active"
    election.data_source_url = "https://results.enr.clarityelections.com/feed.json"
    election.refresh_interval_seconds = 120
    election.ballot_item_id = None
    election.last_refreshed_at = None
    election.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    election.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    election.result = None
    for key, value in overrides.items():
        setattr(election, key, value)
    return election


def _mock_election_result(**overrides: object) -> MagicMock:
    """Create a mock ElectionResult ORM instance."""
    result = MagicMock()
    result.precincts_participating = 100
    result.precincts_reporting = 95
    result.results_data = [
        {
            "id": "2",
            "name": "Candidate A",
            "politicalParty": "Dem",
            "ballotOrder": 1,
            "voteCount": 1234,
            "groupResults": [
                {"groupName": "Election Day", "voteCount": 800},
            ],
        },
    ]
    result.source_created_at = datetime(2026, 2, 9, 17, 40, 56, tzinfo=UTC)
    result.fetched_at = datetime(2026, 2, 10, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _mock_county_result(county_name: str = "Houston County", **overrides: object) -> MagicMock:
    """Create a mock ElectionCountyResult ORM instance."""
    result = MagicMock()
    result.county_name = county_name
    result.county_name_normalized = county_name.removesuffix(" County")
    result.precincts_participating = 7
    result.precincts_reporting = 5
    result.results_data = [
        {
            "id": "2",
            "name": "Candidate A",
            "politicalParty": "Dem",
            "ballotOrder": 1,
            "voteCount": 42,
            "groupResults": [],
        },
    ]
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


def _mock_session_with_scalar(scalar_result: object) -> AsyncMock:
    """Create mock session returning a specific scalar_one_or_none result."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    session.execute.return_value = result
    return session


def _mock_settings() -> MagicMock:
    """Create mock settings with election config."""
    settings = MagicMock()
    settings.election_allowed_domain_list = ["results.enr.clarityelections.com"]
    return settings


# --- Tests for _ballot_option_to_candidate ---


class TestBallotOptionToCandidate:
    """Tests for _ballot_option_to_candidate()."""

    def test_converts_full_option(self):
        opt = {
            "id": "2",
            "name": "John Doe",
            "politicalParty": "Rep",
            "ballotOrder": 2,
            "voteCount": 500,
            "groupResults": [
                {"groupName": "Election Day", "voteCount": 300},
                {"groupName": "Advance Voting", "voteCount": 200},
            ],
        }
        result = _ballot_option_to_candidate(opt)
        assert isinstance(result, CandidateResult)
        assert result.id == "2"
        assert result.name == "John Doe"
        assert result.political_party == "Rep"
        assert result.ballot_order == 2
        assert result.vote_count == 500
        assert len(result.group_results) == 2
        assert isinstance(result.group_results[0], VoteMethodResult)
        assert result.group_results[0].group_name == "Election Day"

    def test_handles_missing_fields(self):
        result = _ballot_option_to_candidate({})
        assert result.id == ""
        assert result.name == ""
        assert result.political_party == ""
        assert result.ballot_order == 1
        assert result.vote_count == 0
        assert result.group_results == []


# --- Tests for build_detail_response ---


class TestBuildDetailResponse:
    """Tests for build_detail_response()."""

    def test_builds_response_without_result(self):
        election = _mock_election()
        response = build_detail_response(election)

        assert isinstance(response, ElectionDetailResponse)
        assert response.id == election.id
        assert response.name == election.name
        assert response.election_date == election.election_date
        assert response.precincts_reporting is None
        assert response.precincts_participating is None

    def test_builds_response_with_result(self):
        result = _mock_election_result()
        election = _mock_election(result=result)
        response = build_detail_response(election)

        assert response.precincts_reporting == 95
        assert response.precincts_participating == 100

    def test_includes_admin_fields(self):
        election = _mock_election()
        response = build_detail_response(election)

        assert response.data_source_url == election.data_source_url
        assert response.refresh_interval_seconds == election.refresh_interval_seconds
        assert response.created_at == election.created_at
        assert response.updated_at == election.updated_at


# --- Tests for create_election ---


class TestCreateElection:
    """Tests for create_election()."""

    @pytest.mark.asyncio
    async def test_creates_new_election(self):
        session = _mock_session_with_scalar(None)  # no existing

        request = ElectionCreateRequest(
            name="Test Election",
            election_date=date(2026, 2, 17),
            election_type="special",
            district="State Senate - District 18",
            data_source_url="https://results.enr.clarityelections.com/feed.json",
            refresh_interval_seconds=120,
        )

        await create_election(session, request)
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_raises_value_error(self):
        existing = _mock_election()
        session = _mock_session_with_scalar(existing)

        request = ElectionCreateRequest(
            name="Test Election",
            election_date=date(2026, 2, 17),
            election_type="special",
            district="State Senate - District 18",
            data_source_url="https://results.enr.clarityelections.com/feed.json",
        )

        with pytest.raises(DuplicateElectionError, match="already exists"):
            await create_election(session, request)

    @pytest.mark.asyncio
    async def test_creates_election_with_ballot_item_id(self):
        """create_election sets ballot_item_id when provided."""
        session = _mock_session_with_scalar(None)

        request = ElectionCreateRequest(
            name="Test Election - PSC District 2",
            election_date=date(2026, 2, 17),
            election_type="special",
            district="PSC - District 2",
            data_source_url="https://results.sos.ga.gov/feed.json",
            ballot_item_id="S10",
        )

        await create_election(session, request)
        session.add.assert_called_once()
        added_election = session.add.call_args[0][0]
        assert added_election.ballot_item_id == "S10"

    @pytest.mark.asyncio
    async def test_duplicate_ballot_item_id_raises(self):
        """Duplicate detection uses data_source_url + ballot_item_id when ballot_item_id set."""
        existing = _mock_election(ballot_item_id="S10")
        session = _mock_session_with_scalar(existing)

        request = ElectionCreateRequest(
            name="Test Election - PSC District 2",
            election_date=date(2026, 2, 17),
            election_type="special",
            district="PSC - District 2",
            data_source_url="https://results.sos.ga.gov/feed.json",
            ballot_item_id="S10",
        )

        with pytest.raises(DuplicateElectionError, match="ballot item 'S10'"):
            await create_election(session, request)


# --- Tests for get_election_by_id ---


class TestGetElectionById:
    """Tests for get_election_by_id()."""

    @pytest.mark.asyncio
    async def test_returns_election(self):
        election = _mock_election()
        session = _mock_session_with_scalar(election)

        result = await get_election_by_id(session, election.id)
        assert result is election

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session_with_scalar(None)

        result = await get_election_by_id(session, uuid.uuid4())
        assert result is None


# --- Tests for update_election ---


class TestUpdateElection:
    """Tests for update_election()."""

    @pytest.mark.asyncio
    async def test_updates_election(self):
        election = _mock_election()
        session = _mock_session_with_scalar(election)

        from voter_api.schemas.election import ElectionUpdateRequest

        request = ElectionUpdateRequest(name="Updated Name")
        result = await update_election(session, election.id, request)

        assert result is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session_with_scalar(None)

        from voter_api.schemas.election import ElectionUpdateRequest

        request = ElectionUpdateRequest(name="Updated Name")
        result = await update_election(session, uuid.uuid4(), request)

        assert result is None


# --- Tests for get_election_results ---


class TestGetElectionResults:
    """Tests for get_election_results()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session_with_scalar(None)
        result = await get_election_results(session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_results_with_candidates(self):
        election_result = _mock_election_result()
        election = _mock_election(result=election_result)
        election_id = election.id

        session = AsyncMock()
        # First execute: get_election_by_id
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        # Second execute: county results query
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [
            _mock_county_result("Houston County"),
        ]
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_election_results(session, election_id)
        assert isinstance(result, ElectionResultsResponse)
        assert result.election_id == election_id
        assert result.precincts_reporting == 95
        assert len(result.candidates) == 1
        assert len(result.county_results) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_results_without_data(self):
        election = _mock_election(result=None)
        election_id = election.id

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_election_results(session, election_id)
        assert result is not None
        assert result.candidates == []
        assert result.county_results == []
        assert result.precincts_reporting is None


# --- Tests for get_raw_election_results ---


class TestGetRawElectionResults:
    """Tests for get_raw_election_results()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session_with_scalar(None)
        result = await get_raw_election_results(session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_raw_data_passthrough(self):
        raw_data = [
            {
                "id": "2",
                "name": "Candidate A",
                "politicalParty": "Dem",
                "ballotOrder": 1,
                "voteCount": 1234,
                "groupResults": [
                    {"groupName": "Election Day", "voteCount": 800},
                ],
            },
        ]
        election_result = _mock_election_result(results_data=raw_data)
        election = _mock_election(result=election_result)
        election_id = election.id

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [
            _mock_county_result("Houston County"),
        ]
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_raw_election_results(session, election_id)
        assert isinstance(result, RawElectionResultsResponse)
        assert result.election_id == election_id
        assert result.precincts_reporting == 95
        # Raw data passed through without transformation
        assert result.statewide_results == raw_data
        assert result.statewide_results[0]["politicalParty"] == "Dem"
        assert result.statewide_results[0]["voteCount"] == 1234
        # County results also raw
        assert len(result.county_results) == 1
        assert result.county_results[0].county_name == "Houston County"
        assert result.county_results[0].results[0]["politicalParty"] == "Dem"

    @pytest.mark.asyncio
    async def test_returns_empty_results_without_data(self):
        election = _mock_election(result=None)
        election_id = election.id

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_raw_election_results(session, election_id)
        assert result is not None
        assert result.statewide_results == []
        assert result.county_results == []
        assert result.precincts_reporting is None
        assert result.source_created_at is None

    @pytest.mark.asyncio
    async def test_includes_source_created_at(self):
        source_ts = datetime(2026, 2, 9, 17, 40, 56, tzinfo=UTC)
        election_result = _mock_election_result(source_created_at=source_ts)
        election = _mock_election(result=election_result)

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_raw_election_results(session, election.id)
        assert result.source_created_at == source_ts


# --- Tests for _persist_ingestion_result ---


class TestPersistIngestionResult:
    """Tests for _persist_ingestion_result()."""

    @pytest.mark.asyncio
    async def test_creates_new_statewide_result(self):
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        ingestion = IngestionResult(
            statewide=StatewideResultData(
                precincts_participating=100,
                precincts_reporting=95,
                results_data=[{"id": "1", "name": "Candidate"}],
                source_created_at=datetime(2026, 2, 9, tzinfo=UTC),
            ),
            counties=[],
        )

        count = await _persist_ingestion_result(session, uuid.uuid4(), ingestion)
        assert count == 0
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_statewide_result(self):
        session = AsyncMock()
        existing = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing
        session.execute = AsyncMock(return_value=result_mock)

        ingestion = IngestionResult(
            statewide=StatewideResultData(
                precincts_participating=100,
                precincts_reporting=95,
                results_data=[],
                source_created_at=None,
            ),
            counties=[],
        )

        await _persist_ingestion_result(session, uuid.uuid4(), ingestion)
        assert existing.precincts_participating == 100
        assert existing.precincts_reporting == 95
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_creates_county_results(self):
        session = AsyncMock()
        # First call: statewide (no existing), second: county (no existing)
        statewide_mock = MagicMock()
        statewide_mock.scalar_one_or_none.return_value = None
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[statewide_mock, county_mock])

        ingestion = IngestionResult(
            statewide=StatewideResultData(
                precincts_participating=None,
                precincts_reporting=None,
                results_data=[],
                source_created_at=None,
            ),
            counties=[
                CountyResultData(
                    county_name="Houston County",
                    county_name_normalized="Houston",
                    precincts_participating=7,
                    precincts_reporting=5,
                    results_data=[],
                ),
            ],
        )

        count = await _persist_ingestion_result(session, uuid.uuid4(), ingestion)
        assert count == 1
        assert session.add.call_count == 2  # statewide + county

    @pytest.mark.asyncio
    async def test_updates_existing_county_results(self):
        session = AsyncMock()
        statewide_mock = MagicMock()
        statewide_mock.scalar_one_or_none.return_value = None
        existing_county = MagicMock()
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = existing_county
        session.execute = AsyncMock(side_effect=[statewide_mock, county_mock])

        ingestion = IngestionResult(
            statewide=StatewideResultData(
                precincts_participating=None,
                precincts_reporting=None,
                results_data=[],
                source_created_at=None,
            ),
            counties=[
                CountyResultData(
                    county_name="Houston County",
                    county_name_normalized="Houston",
                    precincts_participating=10,
                    precincts_reporting=8,
                    results_data=[{"id": "1"}],
                ),
            ],
        )

        count = await _persist_ingestion_result(session, uuid.uuid4(), ingestion)
        assert count == 1
        assert existing_county.precincts_participating == 10
        assert existing_county.precincts_reporting == 8


# --- Tests for refresh_single_election ---


class TestRefreshSingleElection:
    """Tests for refresh_single_election()."""

    @pytest.mark.asyncio
    async def test_raises_value_error_when_not_found(self):
        session = _mock_session_with_scalar(None)

        with pytest.raises(ValueError, match="Election not found"):
            await refresh_single_election(session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_refreshes_election(self):
        election = _mock_election()
        election_id = election.id

        session = AsyncMock()
        # get_election_by_id
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election

        # _persist_ingestion_result calls (statewide + county mocks)
        statewide_mock = MagicMock()
        statewide_mock.scalar_one_or_none.return_value = None
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = None

        session.execute = AsyncMock(side_effect=[election_query, statewide_mock, county_mock])

        from voter_api.lib.election_tracker.parser import (
            BallotItem,
            BallotOption,
            LocalResult,
            SoSFeed,
            SoSResults,
        )

        mock_feed = SoSFeed(
            electionDate="2026-02-17",
            electionName="Test",
            createdAt="2026-02-09T17:40:56Z",
            results=SoSResults(
                id="s1",
                name="GA",
                ballotItems=[
                    BallotItem(
                        id="b1",
                        name="Race",
                        ballotOptions=[
                            BallotOption(id="1", name="Candidate", voteCount=100),
                        ],
                    ),
                ],
            ),
            localResults=[
                LocalResult(
                    id="c1",
                    name="Houston County",
                    ballotItems=[
                        BallotItem(id="b1", name="Race", ballotOptions=[]),
                    ],
                ),
            ],
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=mock_feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
        ):
            result = await refresh_single_election(session, election_id)

        assert isinstance(result, RefreshResponse)
        assert result.election_id == election_id
        assert result.counties_updated == 1
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_ballot_item_id_to_ingester(self):
        """refresh_single_election passes ballot_item_id to ingest_election_results."""
        election = _mock_election(ballot_item_id="S10")
        election_id = election.id

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election

        statewide_mock = MagicMock()
        statewide_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[election_query, statewide_mock])

        mock_ingestion = IngestionResult(
            statewide=StatewideResultData(
                precincts_participating=100,
                precincts_reporting=95,
                results_data=[],
                source_created_at=None,
            ),
            counties=[],
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.ingest_election_results",
                return_value=mock_ingestion,
            ) as mock_ingest,
        ):
            result = await refresh_single_election(session, election_id)

        mock_ingest.assert_called_once()
        assert mock_ingest.call_args[1]["ballot_item_id"] == "S10"
        assert isinstance(result, RefreshResponse)


# --- Tests for list_elections ---


class TestListElections:
    """Tests for list_elections()."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[count_result, select_result])

        items, total = await list_elections(session)
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_returns_election_summaries(self):
        election = _mock_election()
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [election]
        session.execute = AsyncMock(side_effect=[count_result, select_result])

        items, total = await list_elections(session)
        assert total == 1
        assert len(items) == 1
        assert isinstance(items[0], ElectionSummary)
        assert items[0].name == election.name

    @pytest.mark.asyncio
    async def test_includes_precincts_from_result(self):
        result = _mock_election_result()
        election = _mock_election(result=result)
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [election]
        session.execute = AsyncMock(side_effect=[count_result, select_result])

        items, total = await list_elections(session)
        assert items[0].precincts_reporting == 95
        assert items[0].precincts_participating == 100


# --- Tests for refresh_all_active_elections ---


class TestRefreshAllActiveElections:
    """Tests for refresh_all_active_elections()."""

    @pytest.mark.asyncio
    async def test_refreshes_active_elections(self):
        election = _mock_election()
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [election]
        session.execute = AsyncMock(return_value=query_result)

        with patch(
            "voter_api.services.election_service.refresh_single_election",
            new_callable=AsyncMock,
        ) as mock_refresh:
            count = await refresh_all_active_elections(session)

        assert count == 1
        mock_refresh.assert_awaited_once_with(session, election.id)

    @pytest.mark.asyncio
    async def test_continues_on_failure(self):
        e1 = _mock_election()
        e2 = _mock_election()
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = [e1, e2]
        session.execute = AsyncMock(return_value=query_result)

        with patch(
            "voter_api.services.election_service.refresh_single_election",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("fail"), None],
        ):
            count = await refresh_all_active_elections(session)

        assert count == 1  # second succeeded

    @pytest.mark.asyncio
    async def test_returns_zero_with_no_active(self):
        session = AsyncMock()
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=query_result)

        count = await refresh_all_active_elections(session)
        assert count == 0


# --- Tests for election_refresh_loop ---


class TestElectionRefreshLoop:
    """Tests for election_refresh_loop()."""

    @pytest.mark.asyncio
    async def test_loop_starts_and_cancels(self):
        """Loop starts, sleeps, and cancels cleanly."""
        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "voter_api.core.database.get_session_factory",
                return_value=mock_factory,
            ),
            patch(
                "voter_api.services.election_service.refresh_all_active_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            # Make sleep raise CancelledError on second call to exit loop
            mock_sleep.side_effect = [None, asyncio.CancelledError()]

            task = asyncio.create_task(election_refresh_loop(interval=60))
            await task  # should complete due to CancelledError

    @pytest.mark.asyncio
    async def test_loop_recovers_from_errors(self):
        """Loop continues after non-fatal errors."""
        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        call_count = 0

        async def mock_refresh(session):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("DB error")
            return 1

        with (
            patch(
                "voter_api.core.database.get_session_factory",
                return_value=mock_factory,
            ),
            patch(
                "voter_api.services.election_service.refresh_all_active_elections",
                side_effect=mock_refresh,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            # Three iterations: error, success, cancel
            mock_sleep.side_effect = [None, None, asyncio.CancelledError()]

            task = asyncio.create_task(election_refresh_loop(interval=10))
            await task

        assert call_count == 2  # called twice before cancel


# --- Tests for _transpose_precinct_results ---


class TestTransposePrecinctResults:
    """Tests for _transpose_precinct_results()."""

    def test_single_candidate_single_precinct(self):
        data = [
            {
                "id": "2",
                "name": "Jane Smith",
                "politicalParty": "Dem",
                "ballotOrder": 2,
                "voteCount": 100,
                "precinctResults": [
                    {
                        "id": "ANNX",
                        "name": "Annex",
                        "reportingStatus": "Reported",
                        "voteCount": 10,
                        "groupResults": [{"groupName": "Election Day", "voteCount": 8}],
                    },
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        assert "ANNX" in result
        precinct = result["ANNX"]
        assert precinct["precinct_id"] == "ANNX"
        assert precinct["precinct_name"] == "Annex"
        assert precinct["reporting_status"] == "Reported"
        assert len(precinct["candidates"]) == 1
        cand = precinct["candidates"][0]
        assert isinstance(cand, PrecinctCandidateResult)
        assert cand.id == "2"
        assert cand.name == "Jane Smith"
        assert cand.ballot_order == 2
        assert cand.vote_count == 10
        assert len(cand.group_results) == 1
        assert cand.group_results[0].group_name == "Election Day"

    def test_multiple_candidates_same_precinct(self):
        data = [
            {
                "id": "2",
                "name": "Jane Smith",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 50},
                ],
            },
            {
                "id": "4",
                "name": "John Doe",
                "politicalParty": "Rep",
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 75},
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        assert len(result) == 1
        assert len(result["P01"]["candidates"]) == 2

    def test_null_precinct_results(self):
        data = [
            {"id": "2", "name": "Jane", "precinctResults": None},
        ]
        result = _transpose_precinct_results(data)
        assert result == {}

    def test_empty_precinct_results(self):
        data = [
            {"id": "2", "name": "Jane", "precinctResults": []},
        ]
        result = _transpose_precinct_results(data)
        assert result == {}

    def test_missing_precinct_results_key(self):
        data = [{"id": "2", "name": "Jane"}]
        result = _transpose_precinct_results(data)
        assert result == {}

    def test_uppercases_precinct_id(self):
        data = [
            {
                "id": "2",
                "name": "Jane",
                "precinctResults": [
                    {"id": "annx", "name": "Annex", "voteCount": 5},
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        assert "ANNX" in result
        assert result["ANNX"]["precinct_id"] == "ANNX"

    def test_group_results_preserved(self):
        data = [
            {
                "id": "2",
                "name": "Jane",
                "politicalParty": "Dem",
                "precinctResults": [
                    {
                        "id": "P01",
                        "name": "Precinct 1",
                        "voteCount": 30,
                        "groupResults": [
                            {"groupName": "Advance Voting", "voteCount": 20},
                            {"groupName": "Election Day", "voteCount": 10},
                        ],
                    },
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        cand = result["P01"]["candidates"][0]
        assert len(cand.group_results) == 2
        assert cand.group_results[0].group_name == "Advance Voting"

    def test_skips_empty_precinct_id(self):
        data = [
            {
                "id": "2",
                "name": "Jane",
                "precinctResults": [
                    {"id": "", "name": "Empty", "voteCount": 0},
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        assert result == {}

    def test_ballot_order_defaults_to_one(self):
        data = [
            {
                "id": "2",
                "name": "Jane",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 5},
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        cand = result["P01"]["candidates"][0]
        assert cand.ballot_order == 1

    def test_ballot_order_explicit_value(self):
        data = [
            {
                "id": "2",
                "name": "Jane",
                "politicalParty": "Dem",
                "ballotOrder": 3,
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 5},
                ],
            },
        ]
        result = _transpose_precinct_results(data)
        cand = result["P01"]["candidates"][0]
        assert cand.ballot_order == 3


# --- Tests for get_election_precinct_results_geojson ---


class TestGetElectionPrecinctResultsGeoJSON:
    """Tests for get_election_precinct_results_geojson()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _mock_session_with_scalar(None)
        result = await get_election_precinct_results_geojson(session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_empty_features_when_no_county_results(self):
        election = _mock_election()
        session = AsyncMock()
        # get_election_by_id
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        # county results query (empty)
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[election_query, county_query])

        result = await get_election_precinct_results_geojson(session, election.id)
        assert result is not None
        assert isinstance(result, PrecinctElectionResultFeatureCollection)
        assert result.features == []

    @pytest.mark.asyncio
    async def test_builds_features_with_geometry(self):
        election = _mock_election()
        county_result = _mock_county_result("Houston County")
        county_result.results_data = [
            {
                "id": "2",
                "name": "Jane Smith",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "ANNX", "name": "Annex", "voteCount": 10, "reportingStatus": "Reported"},
                ],
            },
        ]

        mock_meta = MagicMock()
        mock_meta.boundary_id = uuid.uuid4()
        mock_meta.precinct_id = "ANNX"
        mock_meta.precinct_name = "Annex"
        mock_meta.sos_id = None
        mock_meta.county_name = "Houston"

        mock_boundary_row = MagicMock()
        mock_boundary_row.id = mock_meta.boundary_id
        mock_boundary_row.geometry = MagicMock()

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [county_result]
        # metadata query
        meta_query = MagicMock()
        meta_query.scalars.return_value.all.return_value = [mock_meta]
        # geometry query
        geom_query = MagicMock()
        geom_query.all.return_value = [mock_boundary_row]

        session.execute = AsyncMock(side_effect=[election_query, county_query, meta_query, geom_query])

        mock_shape = MagicMock()
        mock_mapping = {"type": "MultiPolygon", "coordinates": []}

        with (
            patch("geoalchemy2.shape.to_shape", return_value=mock_shape),
            patch("shapely.geometry.mapping", return_value=mock_mapping),
        ):
            result = await get_election_precinct_results_geojson(session, election.id)

        assert result is not None
        assert len(result.features) == 1
        feature = result.features[0]
        assert feature.properties["precinct_id"] == "ANNX"
        assert feature.properties["county_name"] == "Houston County"
        assert feature.properties["total_votes"] == 10
        assert feature.geometry == mock_mapping

    @pytest.mark.asyncio
    async def test_null_geometry_for_unmatched_precinct(self):
        election = _mock_election()
        county_result = _mock_county_result("Houston County")
        county_result.results_data = [
            {
                "id": "2",
                "name": "Jane Smith",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "VIRTUAL", "name": "Virtual Precinct", "voteCount": 5},
                ],
            },
        ]

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [county_result]
        # metadata query returns empty (no match)
        meta_query = MagicMock()
        meta_query.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[election_query, county_query, meta_query])

        result = await get_election_precinct_results_geojson(session, election.id)
        assert result is not None
        assert len(result.features) == 0  # null geometries are filtered out

    @pytest.mark.asyncio
    async def test_county_filter(self):
        election = _mock_election()
        county_result = _mock_county_result("Houston County")
        county_result.results_data = [
            {
                "id": "2",
                "name": "Jane",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 5},
                ],
            },
        ]

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [county_result]
        meta_query = MagicMock()
        meta_query.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[election_query, county_query, meta_query])

        result = await get_election_precinct_results_geojson(session, election.id, county="Houston")
        assert result is not None
        assert len(result.features) == 0  # no metadata match → null geometry → filtered out

    @pytest.mark.asyncio
    async def test_uses_county_name_normalized_for_metadata_lookup(self):
        """Verify that the metadata lookup uses county_name_normalized, not county_name."""
        election = _mock_election()
        county_result = _mock_county_result("Houston County")
        county_result.county_name_normalized = "Houston"
        county_result.results_data = [
            {
                "id": "2",
                "name": "Jane",
                "politicalParty": "Dem",
                "precinctResults": [
                    {"id": "P01", "name": "Precinct 1", "voteCount": 5},
                ],
            },
        ]

        session = AsyncMock()
        election_query = MagicMock()
        election_query.scalar_one_or_none.return_value = election
        county_query = MagicMock()
        county_query.scalars.return_value.all.return_value = [county_result]
        meta_query = MagicMock()
        meta_query.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[election_query, county_query, meta_query])

        with patch(
            "voter_api.services.precinct_metadata_service.get_precinct_metadata_by_county_multi_strategy",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_lookup:
            await get_election_precinct_results_geojson(session, election.id)
            mock_lookup.assert_awaited_once_with(session, "Houston", ["P01"], {"P01": "Precinct 1"})
