"""Unit tests for election result ingester."""

import pytest

from voter_api.lib.election_tracker.ingester import (
    CountyResultData,
    IngestionResult,
    StatewideResultData,
    _normalize_county_name,
    ingest_election_results,
)
from voter_api.lib.election_tracker.parser import (
    BallotItem,
    BallotOption,
    GroupResult,
    LocalResult,
    SoSFeed,
    SoSResults,
)


class TestNormalizeCountyName:
    """Tests for _normalize_county_name()."""

    def test_strips_county_suffix(self):
        assert _normalize_county_name("Houston County") == "Houston"

    def test_preserves_name_without_suffix(self):
        assert _normalize_county_name("Houston") == "Houston"

    def test_strips_whitespace(self):
        assert _normalize_county_name("  Houston County  ") == "Houston"

    def test_handles_county_only(self):
        # "County" does not end with " County" (no space prefix), so returned as-is
        assert _normalize_county_name("County") == "County"

    def test_handles_multi_word_county(self):
        assert _normalize_county_name("Ben Hill County") == "Ben Hill"


_DEFAULT_LOCAL_RESULTS = [
    LocalResult(
        id="county-001",
        name="Houston County",
        ballotItems=[
            BallotItem(
                id="SSD18",
                name="State Senate - District 18",
                precinctsParticipating=7,
                precinctsReporting=5,
                ballotOptions=[
                    BallotOption(
                        id="2",
                        name="LeMario Nicholas Brown (Dem)",
                        ballotOrder=1,
                        voteCount=42,
                        politicalParty="Dem",
                        groupResults=[],
                    ),
                ],
            ),
        ],
    ),
]


def _make_feed(
    local_results: list[LocalResult] | None = None,
    precincts_participating: int | None = None,
    precincts_reporting: int | None = None,
) -> SoSFeed:
    """Build a SoSFeed for testing."""
    if local_results is None:
        local_results = _DEFAULT_LOCAL_RESULTS
    return SoSFeed(
        electionDate="2026-02-17",
        electionName="Test Election",
        createdAt="2026-02-09T17:40:56Z",
        results=SoSResults(
            id="state-001",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="SSD18",
                    name="State Senate - District 18",
                    precinctsParticipating=precincts_participating,
                    precinctsReporting=precincts_reporting,
                    ballotOptions=[
                        BallotOption(
                            id="2",
                            name="LeMario Nicholas Brown (Dem)",
                            ballotOrder=1,
                            voteCount=1234,
                            politicalParty="Dem",
                            groupResults=[
                                GroupResult(
                                    groupName="Election Day",
                                    voteCount=800,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
        localResults=local_results,
    )


class TestIngestElectionResults:
    """Tests for ingest_election_results()."""

    def test_returns_ingestion_result(self):
        """Ingestion returns an IngestionResult dataclass."""
        feed = _make_feed()
        result = ingest_election_results(feed)
        assert isinstance(result, IngestionResult)
        assert isinstance(result.statewide, StatewideResultData)
        assert len(result.counties) == 1
        assert isinstance(result.counties[0], CountyResultData)

    def test_extracts_statewide_results(self):
        """Statewide data is correctly extracted."""
        feed = _make_feed(precincts_participating=100, precincts_reporting=95)
        result = ingest_election_results(feed)

        assert result.statewide.precincts_participating == 100
        assert result.statewide.precincts_reporting == 95
        assert len(result.statewide.results_data) == 1
        assert result.statewide.results_data[0]["name"] == "LeMario Nicholas Brown (Dem)"

    def test_extracts_source_created_at(self):
        """Source createdAt is parsed into a datetime."""
        feed = _make_feed()
        result = ingest_election_results(feed)
        assert result.statewide.source_created_at is not None

    def test_county_name_normalization(self):
        """County names have ' County' suffix stripped."""
        feed = _make_feed()
        result = ingest_election_results(feed)

        assert result.counties[0].county_name == "Houston County"
        assert result.counties[0].county_name_normalized == "Houston"

    def test_empty_local_results(self):
        """Feed with no county results returns empty list."""
        feed = _make_feed(local_results=[])
        result = ingest_election_results(feed)
        assert len(result.counties) == 0

    def test_multiple_counties(self):
        """Multiple counties are all extracted."""
        feed = _make_feed(
            local_results=[
                LocalResult(
                    id="county-001",
                    name="Houston County",
                    ballotItems=[
                        BallotItem(
                            id="SSD18",
                            name="State Senate",
                            precinctsParticipating=7,
                            precinctsReporting=5,
                            ballotOptions=[],
                        ),
                    ],
                ),
                LocalResult(
                    id="county-002",
                    name="Peach County",
                    ballotItems=[
                        BallotItem(
                            id="SSD18",
                            name="State Senate",
                            precinctsParticipating=3,
                            precinctsReporting=2,
                            ballotOptions=[],
                        ),
                    ],
                ),
            ]
        )

        result = ingest_election_results(feed)
        assert len(result.counties) == 2
        assert result.counties[0].county_name_normalized == "Houston"
        assert result.counties[1].county_name_normalized == "Peach"

    def test_county_ballot_data_extracted(self):
        """County-level ballot options are extracted into results_data."""
        feed = _make_feed()
        result = ingest_election_results(feed)

        assert len(result.counties[0].results_data) == 1
        assert result.counties[0].results_data[0]["voteCount"] == 42

    def test_county_precincts_extracted(self):
        """County-level precinct counts are extracted."""
        feed = _make_feed()
        result = ingest_election_results(feed)

        assert result.counties[0].precincts_participating == 7
        assert result.counties[0].precincts_reporting == 5

    def test_no_ballot_items_statewide(self):
        """Feed with no statewide ballot items returns empty results_data."""
        feed = SoSFeed(
            electionDate="2026-02-17",
            electionName="Test Election",
            createdAt="2026-02-09T17:40:56Z",
            results=SoSResults(id="state-001", name="Georgia", ballotItems=[]),
            localResults=[],
        )
        result = ingest_election_results(feed)
        assert result.statewide.precincts_participating is None
        assert result.statewide.precincts_reporting is None
        assert result.statewide.results_data == []

    def test_invalid_created_at_sets_none(self):
        """Invalid createdAt string results in None source_created_at."""
        feed = SoSFeed(
            electionDate="2026-02-17",
            electionName="Test",
            createdAt="not-a-date",
            results=SoSResults(id="s1", name="GA", ballotItems=[]),
            localResults=[],
        )
        result = ingest_election_results(feed)
        assert result.statewide.source_created_at is None

    def test_is_synchronous(self):
        """ingest_election_results is a regular function, not a coroutine."""
        import inspect

        assert not inspect.iscoroutinefunction(ingest_election_results)

    def test_no_orm_imports(self):
        """The ingester module has no ORM model imports."""
        import voter_api.lib.election_tracker.ingester as mod

        source = pytest.importorskip("inspect").getsource(mod)
        assert "from voter_api.models" not in source
        assert "AsyncSession" not in source
