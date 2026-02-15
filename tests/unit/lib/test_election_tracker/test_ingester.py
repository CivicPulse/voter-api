"""Unit tests for election result ingester."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.lib.election_tracker.ingester import _normalize_county_name, ingest_election_results
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

    @pytest.mark.asyncio
    async def test_creates_statewide_result(self):
        """First ingest creates a new ElectionResult row."""
        session = AsyncMock()
        # Mock: no existing result
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        # Mock: no existing county result
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[result_mock, county_mock])

        election_id = uuid.uuid4()
        feed = _make_feed()

        count = await ingest_election_results(session, election_id, feed)
        assert count == 1
        # session.add called for statewide result and county result
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_statewide_result(self):
        """Re-ingest updates the existing row."""
        session = AsyncMock()
        existing_result = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = existing_result
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[result_mock, county_mock])

        election_id = uuid.uuid4()
        feed = _make_feed()

        count = await ingest_election_results(session, election_id, feed)
        assert count == 1
        # Only county result added (statewide was updated in place)
        assert session.add.call_count == 1
        # Verify statewide result was updated
        assert existing_result.results_data is not None

    @pytest.mark.asyncio
    async def test_county_name_normalization(self):
        """County names have ' County' suffix stripped."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[result_mock, county_mock])

        election_id = uuid.uuid4()
        feed = _make_feed()

        await ingest_election_results(session, election_id, feed)

        # Check the county result that was added
        add_calls = session.add.call_args_list
        county_result_arg = add_calls[1][0][0]  # second add call
        assert county_result_arg.county_name == "Houston County"
        assert county_result_arg.county_name_normalized == "Houston"

    @pytest.mark.asyncio
    async def test_updates_existing_county_result(self):
        """Re-ingest updates existing county rows in place."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        existing_county = MagicMock()
        county_mock = MagicMock()
        county_mock.scalar_one_or_none.return_value = existing_county
        session.execute = AsyncMock(side_effect=[result_mock, county_mock])

        election_id = uuid.uuid4()
        feed = _make_feed()

        count = await ingest_election_results(session, election_id, feed)
        assert count == 1
        # Only statewide result added (county was updated in place)
        assert session.add.call_count == 1
        assert existing_county.results_data is not None

    @pytest.mark.asyncio
    async def test_empty_local_results(self):
        """Feed with no county results returns 0."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        election_id = uuid.uuid4()
        feed = _make_feed(local_results=[])

        count = await ingest_election_results(session, election_id, feed)
        assert count == 0

    @pytest.mark.asyncio
    async def test_multiple_counties(self):
        """Multiple counties are all ingested."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        county_mock1 = MagicMock()
        county_mock1.scalar_one_or_none.return_value = None
        county_mock2 = MagicMock()
        county_mock2.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[result_mock, county_mock1, county_mock2])

        election_id = uuid.uuid4()
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

        count = await ingest_election_results(session, election_id, feed)
        assert count == 2
