"""Unit tests for election result ingester."""

import pytest

from voter_api.lib.election_tracker.ingester import (
    CountyResultData,
    IngestionResult,
    StatewideResultData,
    _find_ballot_item,
    _normalize_county_name,
    detect_election_type,
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


# --- Multi-race helpers ---


def _make_multi_race_feed() -> SoSFeed:
    """Build a SoSFeed with multiple ballot items for multi-race tests."""
    return SoSFeed(
        electionDate="2025-11-04",
        electionName="Multi-Race Election",
        createdAt="2025-11-04T20:00:00Z",
        results=SoSResults(
            id="state-001",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="S10",
                    name="PSC - District 2",
                    precinctsParticipating=4000,
                    precinctsReporting=3500,
                    ballotOptions=[
                        BallotOption(
                            id="c1",
                            name="Tim Echols (I) (Rep)",
                            ballotOrder=1,
                            voteCount=582402,
                            politicalParty="Rep",
                        ),
                    ],
                ),
                BallotItem(
                    id="S11",
                    name="PSC - District 3",
                    precinctsParticipating=4000,
                    precinctsReporting=3600,
                    ballotOptions=[
                        BallotOption(
                            id="c2",
                            name="Fitz Johnson (I) (Rep)",
                            ballotOrder=1,
                            voteCount=578476,
                            politicalParty="Rep",
                        ),
                    ],
                ),
                BallotItem(
                    id="S12",
                    name="State House - District 106",
                    precinctsParticipating=50,
                    precinctsReporting=45,
                    ballotOptions=[
                        BallotOption(
                            id="c3",
                            name="Muhammad Akbar Ali (Dem)",
                            ballotOrder=1,
                            voteCount=2613,
                            politicalParty="Dem",
                        ),
                    ],
                ),
            ],
        ),
        localResults=[
            LocalResult(
                id="county-001",
                name="Fulton County",
                ballotItems=[
                    BallotItem(
                        id="S10",
                        name="PSC - District 2",
                        ballotOptions=[
                            BallotOption(id="c1", name="Tim Echols", voteCount=100, politicalParty="Rep"),
                        ],
                    ),
                    BallotItem(
                        id="S11",
                        name="PSC - District 3",
                        ballotOptions=[
                            BallotOption(id="c2", name="Fitz Johnson", voteCount=200, politicalParty="Rep"),
                        ],
                    ),
                    BallotItem(
                        id="S12",
                        name="State House - District 106",
                        ballotOptions=[
                            BallotOption(id="c3", name="Muhammad Akbar Ali", voteCount=50, politicalParty="Dem"),
                        ],
                    ),
                ],
            ),
            LocalResult(
                id="county-002",
                name="Pulaski County",
                ballotItems=[
                    BallotItem(
                        id="S10",
                        name="PSC - District 2",
                        ballotOptions=[
                            BallotOption(id="c1", name="Tim Echols", voteCount=30, politicalParty="Rep"),
                        ],
                    ),
                    BallotItem(
                        id="S11",
                        name="PSC - District 3",
                        ballotOptions=[
                            BallotOption(id="c2", name="Fitz Johnson", voteCount=40, politicalParty="Rep"),
                        ],
                    ),
                    # Note: No S12 — Pulaski doesn't have the State House race
                ],
            ),
        ],
    )


class TestFindBallotItem:
    """Tests for _find_ballot_item()."""

    def test_returns_first_when_id_none(self):
        items = [
            BallotItem(id="S10", name="Race 1"),
            BallotItem(id="S11", name="Race 2"),
        ]
        result = _find_ballot_item(items, None, "test")
        assert result is not None
        assert result.id == "S10"

    def test_finds_by_id(self):
        items = [
            BallotItem(id="S10", name="Race 1"),
            BallotItem(id="S11", name="Race 2"),
        ]
        result = _find_ballot_item(items, "S11", "test")
        assert result is not None
        assert result.id == "S11"

    def test_returns_none_when_items_empty(self):
        result = _find_ballot_item([], None, "test")
        assert result is None

    def test_raises_when_items_empty_with_id(self):
        """Empty items list with a ballot_item_id raises ValueError by default."""
        with pytest.raises(ValueError, match="No ballot items found"):
            _find_ballot_item([], "S10", "test")

    def test_raises_when_id_not_found(self):
        items = [BallotItem(id="S10", name="Race 1")]
        with pytest.raises(ValueError, match="Ballot item 'S99' not found in test"):
            _find_ballot_item(items, "S99", "test", raise_on_missing=True)

    def test_returns_none_when_id_not_found_and_no_raise(self):
        items = [BallotItem(id="S10", name="Race 1")]
        result = _find_ballot_item(items, "S99", "test", raise_on_missing=False)
        assert result is None

    def test_error_message_includes_available_ids(self):
        items = [
            BallotItem(id="S10", name="Race 1"),
            BallotItem(id="S11", name="Race 2"),
        ]
        with pytest.raises(ValueError, match=r"Available: \['S10', 'S11'\]"):
            _find_ballot_item(items, "S99", "statewide", raise_on_missing=True)

    def test_empty_list_with_id_and_raise_on_missing(self):
        """Empty items list raises ValueError when ballot_item_id specified and raise_on_missing=True."""
        with pytest.raises(ValueError, match="No ballot items found"):
            _find_ballot_item([], "S10", "statewide", raise_on_missing=True)

    def test_empty_list_with_id_no_raise(self):
        """Empty items list returns None when raise_on_missing=False even with ballot_item_id."""
        result = _find_ballot_item([], "S10", "test", raise_on_missing=False)
        assert result is None

    def test_empty_list_without_id_and_raise_on_missing(self):
        """Empty items list returns None when ballot_item_id is None, even with raise_on_missing=True."""
        result = _find_ballot_item([], None, "test", raise_on_missing=True)
        assert result is None


class TestIngestMultiRace:
    """Tests for ingest_election_results() with ballot_item_id."""

    def test_backward_compat_defaults_to_first(self):
        """Without ballot_item_id, extracts first ballot item (backward compat)."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed)

        assert result.statewide.precincts_participating == 4000
        assert result.statewide.precincts_reporting == 3500
        assert result.statewide.results_data[0]["name"] == "Tim Echols (I) (Rep)"

    def test_extracts_specific_ballot_item(self):
        """With ballot_item_id, extracts that specific race."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed, ballot_item_id="S11")

        assert result.statewide.precincts_participating == 4000
        assert result.statewide.precincts_reporting == 3600
        assert result.statewide.results_data[0]["name"] == "Fitz Johnson (I) (Rep)"

    def test_extracts_third_ballot_item(self):
        """Can extract the third ballot item."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed, ballot_item_id="S12")

        assert result.statewide.precincts_participating == 50
        assert result.statewide.precincts_reporting == 45
        assert result.statewide.results_data[0]["name"] == "Muhammad Akbar Ali (Dem)"

    def test_raises_for_invalid_ballot_item_id(self):
        """Raises ValueError if ballot_item_id not in statewide results."""
        feed = _make_multi_race_feed()
        with pytest.raises(ValueError, match="Ballot item 'S99' not found in statewide results"):
            ingest_election_results(feed, ballot_item_id="S99")

    def test_skips_counties_without_ballot_item(self):
        """Counties missing the targeted race are silently skipped."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed, ballot_item_id="S12")

        # Fulton has S12, Pulaski does not
        assert len(result.counties) == 1
        assert result.counties[0].county_name == "Fulton County"

    def test_all_counties_included_for_statewide_race(self):
        """Statewide race (S10) includes all counties."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed, ballot_item_id="S10")

        assert len(result.counties) == 2
        county_names = {c.county_name_normalized for c in result.counties}
        assert county_names == {"Fulton", "Pulaski"}

    def test_county_data_matches_targeted_race(self):
        """County results contain data for the targeted race, not the first."""
        feed = _make_multi_race_feed()
        result = ingest_election_results(feed, ballot_item_id="S11")

        # Both counties should have S11 data
        assert len(result.counties) == 2
        fulton = next(c for c in result.counties if c.county_name_normalized == "Fulton")
        assert fulton.results_data[0]["name"] == "Fitz Johnson"
        assert fulton.results_data[0]["voteCount"] == 200


class TestDetectElectionType:
    """Tests for detect_election_type()."""

    def test_general_election(self):
        assert detect_election_type("November General Election") == "general"

    def test_primary_election(self):
        assert detect_election_type("May Primary Election") == "primary"

    def test_runoff_election(self):
        assert detect_election_type("December Runoff Election") == "runoff"

    def test_special_election_fallback(self):
        assert detect_election_type("January 20 Special Election") == "special"

    def test_special_election_runoff_returns_runoff(self):
        """'Special Election Runoff' matches runoff first due to priority."""
        assert detect_election_type("Special Election Runoff") == "runoff"

    def test_case_insensitive(self):
        assert detect_election_type("GENERAL ELECTION") == "general"
        assert detect_election_type("primary election") == "primary"
        assert detect_election_type("Runoff Election") == "runoff"

    def test_unknown_name_defaults_to_special(self):
        assert detect_election_type("Some Unknown Election") == "special"

    def test_empty_string_defaults_to_special(self):
        assert detect_election_type("") == "special"

    def test_primary_runoff_returns_runoff(self):
        """'Primary Runoff' matches runoff first due to priority."""
        assert detect_election_type("Primary Runoff") == "runoff"

    def test_real_sos_feed_names(self):
        """Test against actual GA SoS feed election names."""
        assert detect_election_type("January20SpecialElection") == "special"
        assert detect_election_type("November 5 General Election") == "general"
        assert detect_election_type("May 21 Primary Election") == "primary"
        assert detect_election_type("June 18 Runoff") == "runoff"
