"""Unit tests for voter history service query functions.

Tests the query and aggregation functions using mocked sessions, covering
get_voter_history, list_election_participants, get_participation_stats,
get_participation_summary, and _get_election_or_raise.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.models.election import Election
from voter_api.models.voter_history import VoterHistory
from voter_api.services.voter_history_service import (
    _build_election_match_conditions,
    _get_election_or_raise,
    get_participation_stats,
    get_participation_summary,
    get_voter_history,
    list_election_participants,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session_with_scalars(
    scalars_result: list,
    scalar_one_value: int = 0,
) -> AsyncMock:
    """Create a mock session for queries returning scalars and a count."""
    session = AsyncMock()

    # First execute call returns count (scalar_one)
    count_result = MagicMock()
    count_result.scalar_one.return_value = scalar_one_value

    # Second execute call returns records (scalars().all())
    records_result = MagicMock()
    records_mock = MagicMock()
    records_mock.all.return_value = scalars_result
    records_result.scalars.return_value = records_mock

    session.execute.side_effect = [count_result, records_result]
    return session


def _mock_voter_history(**overrides) -> MagicMock:
    """Create a mock VoterHistory model."""
    defaults = {
        "id": uuid.uuid4(),
        "voter_registration_number": "12345678",
        "county": "FULTON",
        "election_date": date(2024, 11, 5),
        "election_type": "GENERAL ELECTION",
        "normalized_election_type": "general",
        "party": "NP",
        "ballot_style": "STD",
        "absentee": False,
        "provisional": False,
        "supplemental": False,
    }
    defaults.update(overrides)
    record = MagicMock(spec=VoterHistory)
    for k, v in defaults.items():
        setattr(record, k, v)
    return record


def _mock_election(**overrides) -> MagicMock:
    """Create a mock Election model."""
    defaults = {
        "id": uuid.uuid4(),
        "election_date": date(2024, 11, 5),
        "election_type": "general",
        "name": "General Election - 11/05/2024",
    }
    defaults.update(overrides)
    election = MagicMock(spec=Election)
    for k, v in defaults.items():
        setattr(election, k, v)
    return election


# ---------------------------------------------------------------------------
# get_voter_history
# ---------------------------------------------------------------------------


class TestGetVoterHistory:
    """Tests for get_voter_history query function."""

    @pytest.mark.asyncio
    async def test_returns_records_and_count(self) -> None:
        """Returns matching records and total count."""
        records = [_mock_voter_history(), _mock_voter_history()]
        session = _mock_session_with_scalars(records, scalar_one_value=2)

        result_records, total = await get_voter_history(session, "12345678")

        assert total == 2
        assert len(result_records) == 2
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        """Empty result set returns zero count and empty list."""
        session = _mock_session_with_scalars([], scalar_one_value=0)

        records, total = await get_voter_history(session, "99999999")

        assert total == 0
        assert records == []

    @pytest.mark.asyncio
    async def test_with_filters(self) -> None:
        """Filters are applied (session.execute is called with the right queries)."""
        session = _mock_session_with_scalars([], scalar_one_value=0)

        await get_voter_history(
            session,
            "12345678",
            election_type="GENERAL ELECTION",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
            county="FULTON",
            ballot_style="STD",
        )

        # Two execute calls (count + records)
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        """Pagination params are applied."""
        records = [_mock_voter_history()]
        session = _mock_session_with_scalars(records, scalar_one_value=50)

        _, total = await get_voter_history(session, "12345678", page=3, page_size=10)

        assert total == 50


# ---------------------------------------------------------------------------
# list_election_participants
# ---------------------------------------------------------------------------


class TestListElectionParticipants:
    """Tests for list_election_participants query function."""

    @pytest.mark.asyncio
    async def test_returns_participants(self) -> None:
        """Returns participants for a valid election."""
        election = _mock_election()
        records = [_mock_voter_history()]

        session = AsyncMock()
        # First call: get election
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        # Second call: _build_election_match_conditions COUNT
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # Third call: count
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # Fourth call: records
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = records
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [election_result, match_count_result, count_result, records_result]

        result_records, total = await list_election_participants(session, election.id)

        assert total == 1
        assert len(result_records) == 1

    @pytest.mark.asyncio
    async def test_election_not_found_raises(self) -> None:
        """Raises ValueError when election does not exist."""
        session = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        session.execute.return_value = not_found_result

        with pytest.raises(ValueError, match="Election not found"):
            await list_election_participants(session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_with_filters(self) -> None:
        """Filters are applied correctly."""
        election = _mock_election()
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = []
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [election_result, match_count_result, count_result, records_result]

        records, total = await list_election_participants(
            session,
            election.id,
            county="FULTON",
            ballot_style="STD",
            absentee=True,
            provisional=False,
            supplemental=True,
        )

        assert total == 0
        assert records == []
        # 4 execute calls: election lookup + match count + count + records
        assert session.execute.await_count == 4


# ---------------------------------------------------------------------------
# get_participation_stats
# ---------------------------------------------------------------------------


class TestGetParticipationStats:
    """Tests for get_participation_stats aggregate function."""

    @pytest.mark.asyncio
    async def test_returns_stats(self) -> None:
        """Returns stats with breakdowns."""
        election = _mock_election()
        eid = election.id

        session = AsyncMock()
        # 1: election lookup
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        # 2: _build_election_match_conditions COUNT
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # 3: total count
        total_result = MagicMock()
        total_result.scalar_one.return_value = 100
        # 4: by county
        county_result = MagicMock()
        county_result.all.return_value = [("FULTON", 60), ("DEKALB", 40)]
        # 5: by ballot style
        style_result = MagicMock()
        style_result.all.return_value = [("STD", 80), ("ABSENTEE", 20)]

        session.execute.side_effect = [
            election_result,
            match_count_result,
            total_result,
            county_result,
            style_result,
        ]

        stats = await get_participation_stats(session, eid)

        assert stats.election_id == eid
        assert stats.total_participants == 100
        assert len(stats.by_county) == 2
        assert stats.by_county[0].county == "FULTON"
        assert stats.by_county[0].count == 60
        assert len(stats.by_ballot_style) == 2

    @pytest.mark.asyncio
    async def test_election_not_found_raises(self) -> None:
        """Raises ValueError when election does not exist."""
        session = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        session.execute.return_value = not_found_result

        with pytest.raises(ValueError, match="Election not found"):
            await get_participation_stats(session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_empty_stats(self) -> None:
        """Election with no participants returns zero counts."""
        election = _mock_election()

        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        county_result = MagicMock()
        county_result.all.return_value = []
        style_result = MagicMock()
        style_result.all.return_value = []

        session.execute.side_effect = [
            election_result,
            match_count_result,
            total_result,
            county_result,
            style_result,
        ]

        stats = await get_participation_stats(session, election.id)

        assert stats.total_participants == 0
        assert stats.by_county == []
        assert stats.by_ballot_style == []


# ---------------------------------------------------------------------------
# get_participation_summary
# ---------------------------------------------------------------------------


class TestGetParticipationSummary:
    """Tests for get_participation_summary function."""

    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        """Returns summary with count and last date."""
        session = AsyncMock()
        result = MagicMock()
        result.one.return_value = (5, date(2024, 11, 5))
        session.execute.return_value = result

        summary = await get_participation_summary(session, "12345678")

        assert summary.total_elections == 5
        assert summary.last_election_date == date(2024, 11, 5)

    @pytest.mark.asyncio
    async def test_no_history_returns_defaults(self) -> None:
        """Voter with no history returns zero elections and null date."""
        session = AsyncMock()
        result = MagicMock()
        result.one.return_value = (0, None)
        session.execute.return_value = result

        summary = await get_participation_summary(session, "99999999")

        assert summary.total_elections == 0
        assert summary.last_election_date is None


# ---------------------------------------------------------------------------
# _get_election_or_raise
# ---------------------------------------------------------------------------


class TestGetElectionOrRaise:
    """Tests for the _get_election_or_raise helper."""

    @pytest.mark.asyncio
    async def test_returns_election(self) -> None:
        """Returns election when found."""
        election = _mock_election()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = election
        session.execute.return_value = result

        found = await _get_election_or_raise(session, election.id)

        assert found is election

    @pytest.mark.asyncio
    async def test_raises_value_error_when_not_found(self) -> None:
        """Raises ValueError when election not found."""
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        with pytest.raises(ValueError, match="Election not found"):
            await _get_election_or_raise(session, uuid.uuid4())


# ---------------------------------------------------------------------------
# _build_election_match_conditions
# ---------------------------------------------------------------------------


class TestBuildElectionMatchConditions:
    """Tests for the _build_election_match_conditions helper."""

    @pytest.mark.asyncio
    async def test_single_election_on_date_matches_by_date_only(self) -> None:
        """When only one election on the date, matches by date only."""
        election = _mock_election(
            election_date=date(2026, 2, 17),
            election_type="special",
        )
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        session.execute.return_value = count_result

        conditions = await _build_election_match_conditions(session, election)

        # Only date condition — no type condition
        assert len(conditions) == 1

    @pytest.mark.asyncio
    async def test_multiple_elections_on_date_matches_by_date_and_type(self) -> None:
        """When multiple elections on the date, matches by date + type."""
        election = _mock_election(
            election_date=date(2024, 5, 21),
            election_type="primary",
        )
        session = AsyncMock()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        session.execute.return_value = count_result

        conditions = await _build_election_match_conditions(session, election)

        # Both date and type conditions
        assert len(conditions) == 2

    @pytest.mark.asyncio
    async def test_participants_with_type_mismatch_single_election(self) -> None:
        """Type="special" election finds voter_history with normalized_type="runoff" via date-only match."""
        election = _mock_election(
            election_date=date(2026, 2, 17),
            election_type="special",
        )
        records = [
            _mock_voter_history(
                election_date=date(2026, 2, 17),
                normalized_election_type="runoff",
            )
        ]

        session = AsyncMock()
        # 1: election lookup
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        # 2: _build_election_match_conditions COUNT — single election
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # 3: count query — finds records via date-only match
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # 4: records query
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = records
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [
            election_result,
            match_count_result,
            count_result,
            records_result,
        ]

        result_records, total = await list_election_participants(session, election.id)

        assert total == 1
        assert len(result_records) == 1
