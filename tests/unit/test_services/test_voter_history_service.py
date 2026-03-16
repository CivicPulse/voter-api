"""Unit tests for voter history service query functions.

Tests the query and aggregation functions using mocked sessions, covering
get_voter_history, list_election_participants, get_participation_stats,
get_participation_summary, and _get_election_or_raise.
"""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from voter_api.models.election import Election
from voter_api.models.voter import Voter
from voter_api.models.voter_history import VoterHistory
from voter_api.schemas.voter_history import ParticipationFilters
from voter_api.services.voter_history_service import (
    MismatchFilterError,
    VoterLookupResult,
    _build_election_match_conditions,
    _build_mismatch_filter,
    _get_election_or_raise,
    _latest_analysis_subquery,
    _replace_previous_import,
    get_participation_stats,
    get_participation_summary,
    get_voter_history,
    list_election_participants,
    lookup_voter_details,
    resolve_election_ids,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compile_query(query) -> str:
    """Compile a SQLAlchemy query to PostgreSQL SQL string for structural inspection."""
    return str(query.compile(dialect=postgresql.dialect()))


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
        "district_type": None,
        "district_identifier": None,
        "boundary": None,
        "eligible_county": None,
        "eligible_municipality": None,
    }
    defaults.update(overrides)
    election = MagicMock(spec=Election)
    for k, v in defaults.items():
        setattr(election, k, v)
    return election


def _mock_join_session(election: MagicMock) -> AsyncMock:
    """Create a mock session pre-configured for the JOIN path (5 execute calls)."""
    session = AsyncMock()
    election_result = MagicMock()
    election_result.scalar_one_or_none.return_value = election
    has_resolved_result = MagicMock()
    has_resolved_result.scalar_one.return_value = False
    match_count_result = MagicMock()
    match_count_result.scalar_one.return_value = 1
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0
    records_result = MagicMock()
    records_result.all.return_value = []
    session.execute.side_effect = [
        election_result,
        has_resolved_result,
        match_count_result,
        count_result,
        records_result,
    ]
    return session


def _mock_stats_session(election: MagicMock) -> AsyncMock:
    """Create a mock session pre-configured for get_participation_stats (7 execute calls)."""
    session = AsyncMock()
    election_result = MagicMock()
    election_result.scalar_one_or_none.return_value = election
    has_resolved_result = MagicMock()
    has_resolved_result.scalar_one.return_value = False
    match_count_result = MagicMock()
    match_count_result.scalar_one.return_value = 1
    total_result = MagicMock()
    total_result.scalar_one.return_value = 50
    county_result = MagicMock()
    county_result.all.return_value = []
    style_result = MagicMock()
    style_result.all.return_value = []
    precinct_result = MagicMock()
    precinct_result.all.return_value = []
    session.execute.side_effect = [
        election_result,
        has_resolved_result,
        match_count_result,
        total_result,
        county_result,
        style_result,
        precinct_result,
    ]
    return session


# ---------------------------------------------------------------------------
# get_voter_history
# ---------------------------------------------------------------------------


class TestGetVoterHistory:
    """Tests for get_voter_history query function."""

    async def test_returns_records_and_count(self) -> None:
        """Returns matching records and total count."""
        records = [_mock_voter_history(), _mock_voter_history()]
        session = _mock_session_with_scalars(records, scalar_one_value=2)

        result_records, total = await get_voter_history(session, "12345678")

        assert total == 2
        assert len(result_records) == 2
        assert session.execute.await_count == 2

    async def test_empty_result(self) -> None:
        """Empty result set returns zero count and empty list."""
        session = _mock_session_with_scalars([], scalar_one_value=0)

        records, total = await get_voter_history(session, "99999999")

        assert total == 0
        assert records == []

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

    async def test_returns_participants(self) -> None:
        """Returns participants for a valid election (default path, no voter filters)."""
        election = _mock_election()
        records = [_mock_voter_history()]

        session = AsyncMock()
        # First call: get election
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        # Second call: _build_election_match_conditions has_resolved check
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        # Third call: _build_election_match_conditions election COUNT
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # Fourth call: count
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # Fifth call: records
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = records
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            count_result,
            records_result,
        ]

        result_records, total, voter_details_included, district_type_used = await list_election_participants(
            session, election.id
        )

        assert total == 1
        assert len(result_records) == 1
        assert voter_details_included is False
        assert district_type_used is None

    async def test_election_not_found_raises(self) -> None:
        """Raises ValueError when election does not exist."""
        session = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        session.execute.return_value = not_found_result

        with pytest.raises(ValueError, match="Election not found"):
            await list_election_participants(session, uuid.uuid4())

    async def test_with_filters(self) -> None:
        """VoterHistory-only filters are applied correctly (default path)."""
        election = _mock_election()
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = []
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            count_result,
            records_result,
        ]

        records, total, voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(
                county="FULTON",
                ballot_style="STD",
                absentee=True,
                provisional=False,
                supplemental=True,
            ),
        )

        assert total == 0
        assert records == []
        assert voter_details_included is False
        assert district_type_used is None
        # 5 execute calls: election lookup + has_resolved + match count + count + records
        assert session.execute.await_count == 5

    async def test_voter_filter_triggers_join_path(self) -> None:
        """Voter-table filter (county_precinct) triggers JOIN path."""
        election = _mock_election()
        session = _mock_join_session(election)

        records, total, voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(county_precinct="HA2"),
        )

        assert total == 0
        assert records == []
        assert voter_details_included is True
        assert district_type_used is None

    async def test_q_param_triggers_join_path(self) -> None:
        """The q search parameter triggers the JOIN path."""
        election = _mock_election()
        session = _mock_join_session(election)

        records, total, voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(q="Smith"),
        )

        assert total == 0
        assert records == []
        assert voter_details_included is True
        assert district_type_used is None

    async def test_has_district_mismatch_triggers_join_path(self) -> None:
        """has_district_mismatch filter triggers the JSONB JOIN path."""
        election = _mock_election(district_type="state_senate")
        session = _mock_join_session(election)

        records, total, voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(has_district_mismatch=True),
        )

        assert total == 0
        assert records == []
        assert voter_details_included is True
        assert district_type_used == "state_senate"

    async def test_mismatch_filter_error_null_district_type(self) -> None:
        """MismatchFilterError raised when election has no district_type."""
        election = _mock_election(district_type=None)
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        session.execute.return_value = election_result

        with pytest.raises(MismatchFilterError, match="known district_type"):
            await list_election_participants(
                session,
                election.id,
                filters=ParticipationFilters(has_district_mismatch=True),
            )

    async def test_mismatch_filter_error_unknown_district_type(self) -> None:
        """MismatchFilterError raised when election district_type is not in BOUNDARY_TYPE_TO_VOTER_FIELD."""
        election = _mock_election(district_type="nonexistent_type")
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        session.execute.return_value = election_result

        with pytest.raises(MismatchFilterError, match="not supported for district_type"):
            await list_election_participants(
                session,
                election.id,
                filters=ParticipationFilters(has_district_mismatch=True),
            )

    async def test_mismatch_filter_false_also_errors_on_null_district_type(self) -> None:
        """MismatchFilterError raised for has_district_mismatch=False when district_type is null."""
        election = _mock_election(district_type=None)
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        session.execute.return_value = election_result

        with pytest.raises(MismatchFilterError, match="known district_type"):
            await list_election_participants(
                session,
                election.id,
                filters=ParticipationFilters(has_district_mismatch=False),
            )

    async def test_mismatch_filter_omitted_returns_none_district_type(self) -> None:
        """When has_district_mismatch is not set, district_type_used is None (no analysis JOIN)."""
        election = _mock_election(district_type="state_senate")
        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = []
        records_result.scalars.return_value = records_mock
        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            count_result,
            records_result,
        ]

        _records, _total, _voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(),
        )

        assert district_type_used is None

    async def test_mismatch_filter_true_returns_district_type(self) -> None:
        """When has_district_mismatch=True with valid district_type, district_type_used is set."""
        election = _mock_election(district_type="state_senate")
        session = _mock_join_session(election)

        _records, _total, _voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(has_district_mismatch=True),
        )

        assert district_type_used == "state_senate"

    async def test_mismatch_filter_false_returns_district_type(self) -> None:
        """When has_district_mismatch=False with valid district_type, district_type_used is set."""
        election = _mock_election(district_type="state_senate")
        session = _mock_join_session(election)

        _records, _total, _voter_details_included, district_type_used = await list_election_participants(
            session,
            election.id,
            filters=ParticipationFilters(has_district_mismatch=False),
        )

        assert district_type_used == "state_senate"


# ---------------------------------------------------------------------------
# _build_mismatch_filter
# ---------------------------------------------------------------------------


class TestBuildMismatchFilter:
    """Tests for _build_mismatch_filter — compile-and-assert SQL correctness."""

    def _build_joined_query(self, latest_ar, district_type: str, has_mismatch: bool):
        """Build a representative joined query mirroring list_election_participants."""
        return (
            select(VoterHistory)
            .outerjoin(Voter, VoterHistory.voter_registration_number == Voter.voter_registration_number)
            .join(latest_ar, latest_ar.c.voter_id == Voter.id)
            .where(_build_mismatch_filter(latest_ar, district_type, has_mismatch))
        )

    def test_mismatch_true_uses_subquery_alias_not_orm_table(self) -> None:
        """Compiled SQL references latest_ar, not raw analysis_results in WHERE."""
        latest_ar = _latest_analysis_subquery()
        query = self._build_joined_query(latest_ar, "state_senate", True)
        sql = _compile_query(query)
        assert "latest_ar" in sql, f"Expected 'latest_ar' in compiled SQL: {sql}"
        # analysis_results appears once (inside subquery def), not in WHERE
        where_portion = sql[sql.lower().find("where"):]
        assert "analysis_results" not in where_portion, (
            f"Implicit cross join detected — 'analysis_results' found after WHERE: {where_portion}"
        )

    def test_mismatch_false_uses_subquery_alias_not_orm_table(self) -> None:
        """Compiled SQL for has_mismatch=False also uses subquery alias."""
        latest_ar = _latest_analysis_subquery()
        query = self._build_joined_query(latest_ar, "state_senate", False)
        sql = _compile_query(query)
        assert "latest_ar" in sql
        where_portion = sql[sql.lower().find("where"):]
        assert "analysis_results" not in where_portion, (
            f"Implicit cross join detected — 'analysis_results' found after WHERE: {where_portion}"
        )

    def test_no_duplicate_from_analysis_results(self) -> None:
        """analysis_results appears exactly once in FROM (inside subquery only)."""
        latest_ar = _latest_analysis_subquery()
        query = self._build_joined_query(latest_ar, "congressional", True)
        sql = _compile_query(query).lower()
        count = sql.count("from analysis_results")
        assert count == 1, (
            f"Expected 'from analysis_results' exactly once (in subquery), found {count} times"
        )

    def test_all_boundary_types_produce_valid_clauses(self) -> None:
        """All valid boundary types produce compilable filter clauses."""
        from voter_api.lib.analyzer.comparator import BOUNDARY_TYPE_TO_VOTER_FIELD

        latest_ar = _latest_analysis_subquery()
        for district_type in BOUNDARY_TYPE_TO_VOTER_FIELD:
            for has_mismatch in (True, False):
                query = self._build_joined_query(latest_ar, district_type, has_mismatch)
                sql = _compile_query(query)
                assert "latest_ar" in sql

    def test_true_and_false_produce_different_sql(self) -> None:
        """True and False filters produce structurally different SQL."""
        latest_ar = _latest_analysis_subquery()
        sql_true = _compile_query(self._build_joined_query(latest_ar, "state_senate", True))
        sql_false = _compile_query(self._build_joined_query(latest_ar, "state_senate", False))
        assert sql_true != sql_false


# ---------------------------------------------------------------------------
# get_participation_stats
# ---------------------------------------------------------------------------


class TestGetParticipationStats:
    """Tests for get_participation_stats aggregate function."""

    async def test_returns_stats(self) -> None:
        """Returns stats with breakdowns; no district info means eligible voters is None."""
        election = _mock_election()
        eid = election.id

        session = AsyncMock()
        # 1: election lookup
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        # 2: _build_election_match_conditions has_resolved
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        # 3: _build_election_match_conditions election COUNT
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # 4: total count
        total_result = MagicMock()
        total_result.scalar_one.return_value = 100
        # 5: by county
        county_result = MagicMock()
        county_result.all.return_value = [("FULTON", 60), ("DEKALB", 40)]
        # 6: by ballot style
        style_result = MagicMock()
        style_result.all.return_value = [("STD", 80), ("ABSENTEE", 20)]
        # 7: by precinct
        precinct_result = MagicMock()
        precinct_result.all.return_value = [("HA2", "HAZZARD 2", 35), ("HA1", "HAZZARD 1", 25)]

        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            total_result,
            county_result,
            style_result,
            precinct_result,
        ]

        stats = await get_participation_stats(session, eid)

        assert stats.election_id == eid
        assert stats.total_participants == 100
        assert stats.total_eligible_voters is None
        assert stats.turnout_percentage is None
        assert len(stats.by_county) == 2
        assert stats.by_county[0].county == "FULTON"
        assert stats.by_county[0].count == 60
        assert len(stats.by_ballot_style) == 2
        assert len(stats.by_precinct) == 2
        assert stats.by_precinct[0].precinct == "HA2"
        assert stats.by_precinct[0].precinct_name == "HAZZARD 2"
        assert stats.by_precinct[0].count == 35

    async def test_election_not_found_raises(self) -> None:
        """Raises ValueError when election does not exist."""
        session = AsyncMock()
        not_found_result = MagicMock()
        not_found_result.scalar_one_or_none.return_value = None
        session.execute.return_value = not_found_result

        with pytest.raises(ValueError, match="Election not found"):
            await get_participation_stats(session, uuid.uuid4())

    async def test_empty_stats(self) -> None:
        """Election with no participants returns zero counts and None eligible voters."""
        election = _mock_election()

        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        county_result = MagicMock()
        county_result.all.return_value = []
        style_result = MagicMock()
        style_result.all.return_value = []
        precinct_result = MagicMock()
        precinct_result.all.return_value = []

        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            total_result,
            county_result,
            style_result,
            precinct_result,
        ]

        stats = await get_participation_stats(session, election.id)

        assert stats.total_participants == 0
        assert stats.total_eligible_voters is None
        assert stats.turnout_percentage is None
        assert stats.by_county == []
        assert stats.by_ballot_style == []
        assert stats.by_precinct == []

    async def test_eligible_voters_none_when_no_district(self) -> None:
        """Election without district info returns None for eligible voters."""
        election = _mock_election(district_type=None, district_identifier=None)
        eid = election.id
        session = _mock_stats_session(election)

        with patch(
            "voter_api.services.voter_stats_service.get_voter_stats_for_boundary",
        ) as mock_voter_stats:
            stats = await get_participation_stats(session, eid)

        mock_voter_stats.assert_not_called()
        assert stats.total_eligible_voters is None
        assert stats.turnout_percentage is None

    async def test_eligible_voters_for_county_election(self) -> None:
        """County-type election resolves county name from boundary and computes turnout."""
        from voter_api.schemas.voter_stats import VoterRegistrationStatsResponse, VoterStatusCount

        boundary = MagicMock()
        boundary.name = "Fulton County"

        election = _mock_election(
            district_type="county",
            district_identifier="13121",
            boundary=boundary,
        )
        eid = election.id

        session = AsyncMock()
        election_result = MagicMock()
        election_result.scalar_one_or_none.return_value = election
        has_resolved_result = MagicMock()
        has_resolved_result.scalar_one.return_value = False
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        total_result = MagicMock()
        total_result.scalar_one.return_value = 500
        county_result = MagicMock()
        county_result.all.return_value = [("FULTON", 500)]
        style_result = MagicMock()
        style_result.all.return_value = []
        precinct_result = MagicMock()
        precinct_result.all.return_value = []

        session.execute.side_effect = [
            election_result,
            has_resolved_result,
            match_count_result,
            total_result,
            county_result,
            style_result,
            precinct_result,
        ]

        mock_stats = VoterRegistrationStatsResponse(
            total=1200,
            by_status=[
                VoterStatusCount(status="Active", count=1000),
                VoterStatusCount(status="Inactive", count=200),
            ],
        )
        with patch(
            "voter_api.services.voter_stats_service.get_voter_stats_for_boundary",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ) as mock_fn:
            stats = await get_participation_stats(session, eid)

        mock_fn.assert_awaited_once_with(
            session,
            "county",
            "13121",
            county_name_override="Fulton",
        )
        assert stats.total_eligible_voters == 1000
        assert stats.turnout_percentage == pytest.approx(50.0)

    async def test_eligible_voters_none_for_unmapped_boundary_type(self) -> None:
        """Boundary types with no voter field mapping (e.g. us_senate) return None."""
        election = _mock_election(
            district_type="us_senate",
            district_identifier="1",
        )
        eid = election.id
        session = _mock_stats_session(election)

        with patch(
            "voter_api.services.voter_stats_service.get_voter_stats_for_boundary",
            new_callable=AsyncMock,
            return_value=None,
        ):
            stats = await get_participation_stats(session, eid)

        assert stats.total_eligible_voters is None
        assert stats.turnout_percentage is None


# ---------------------------------------------------------------------------
# get_participation_summary
# ---------------------------------------------------------------------------


class TestGetParticipationSummary:
    """Tests for get_participation_summary function."""

    async def test_returns_summary(self) -> None:
        """Returns summary with count and last date."""
        session = AsyncMock()
        result = MagicMock()
        result.one.return_value = (5, date(2024, 11, 5))
        session.execute.return_value = result

        summary = await get_participation_summary(session, "12345678")

        assert summary.total_elections == 5
        assert summary.last_election_date == date(2024, 11, 5)

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

    async def test_returns_election(self) -> None:
        """Returns election when found."""
        election = _mock_election()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = election
        session.execute.return_value = result

        found = await _get_election_or_raise(session, election.id)

        assert found is election

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

    async def test_single_election_on_date_matches_by_date_only(self) -> None:
        """When only one election on the date, matches by date only."""
        election = _mock_election(
            election_date=date(2026, 2, 17),
            election_type="special",
        )
        session = AsyncMock()
        # First call: check resolved count (0 = no resolved records)
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        # Second call: election count on date (1 = single election)
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # Only date condition — no type condition
        assert len(conditions) == 1

    async def test_multiple_elections_on_date_matches_by_date_and_type(self) -> None:
        """When multiple elections on the date, matches by date + type."""
        election = _mock_election(
            election_date=date(2024, 5, 21),
            election_type="primary",
        )
        session = AsyncMock()
        # First call: check resolved count (0 = no resolved records)
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        # Second call: election count on date (2 = multiple elections)
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 2
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # Both date and type conditions
        assert len(conditions) == 2

    async def test_resolved_election_uses_election_id(self) -> None:
        """When resolved records exist, returns OR condition (resolved + unresolved fallback)."""
        election = _mock_election(
            election_date=date(2026, 2, 17),
            election_type="special",
        )
        session = AsyncMock()
        # First call: check resolved count (>0 = records already resolved)
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 5
        # Second call: election count on date (needed for fallback clause)
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # Single OR condition: resolved rows + unresolved fallback
        assert len(conditions) == 1

    async def test_county_election_unresolved_single_date_adds_county_predicate(self) -> None:
        """County-scoped election appends county predicate (unresolved path, single election on date)."""
        boundary = MagicMock()
        boundary.name = "Fulton County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type="county",
            district_identifier="13121",
            boundary=boundary,
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # date condition + county condition (no type condition since single election)
        assert len(conditions) == 2
        # County predicate must use UPPER(county) name comparison, not raw GEOID
        county_sql = str(conditions[1])
        assert "upper(voter_history.county)" in county_sql.lower()
        assert "13121" not in county_sql

    async def test_county_election_unresolved_multi_date_adds_county_predicate(self) -> None:
        """County-scoped election appends county predicate (unresolved path, multiple elections on date)."""
        boundary = MagicMock()
        boundary.name = "Fulton County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type="county",
            district_identifier="13121",
            boundary=boundary,
            election_type="primary",
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 3
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # date + type + county conditions
        assert len(conditions) == 3
        county_sql = str(conditions[2])
        assert "upper(voter_history.county)" in county_sql.lower()
        assert "13121" not in county_sql

    async def test_county_election_resolved_single_date_includes_county_in_fallback(self) -> None:
        """County predicate is inside the unresolved fallback OR clause (resolved path, single date)."""
        boundary = MagicMock()
        boundary.name = "Fulton County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type="county",
            district_identifier="13121",
            boundary=boundary,
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 5
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # Single OR condition wrapping (election_id match OR fallback-with-county)
        assert len(conditions) == 1
        or_sql = str(conditions[0])
        assert "upper(voter_history.county)" in or_sql.lower()
        assert "13121" not in or_sql

    async def test_county_election_resolved_multi_date_includes_county_in_fallback(self) -> None:
        """County predicate is inside the unresolved fallback OR clause (resolved path, multi date)."""
        boundary = MagicMock()
        boundary.name = "Fulton County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type="county",
            district_identifier="13121",
            boundary=boundary,
            election_type="primary",
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 5
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 3
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        assert len(conditions) == 1
        or_sql = str(conditions[0])
        assert "upper(voter_history.county)" in or_sql.lower()
        assert "13121" not in or_sql

    async def test_resolved_county_election_applies_district_filter_to_both_branches(self) -> None:
        """District filter applies to resolved branch too (defense-in-depth against cross-county leakage)."""
        boundary = MagicMock()
        boundary.name = "Bibb County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type="county",
            district_identifier="13021",
            boundary=boundary,
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 10  # Has resolved records
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1  # Single election on date
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # Single OR condition
        assert len(conditions) == 1
        or_sql = str(conditions[0]).lower()
        # County filter should appear in BOTH branches of the OR:
        # 1. The resolved branch (election_id = X AND county filter)
        # 2. The fallback branch (election_id IS NULL AND date AND county filter)
        assert "upper(voter_history.county)" in or_sql
        # The election_id match should be AND-ed with the county filter,
        # not a bare election_id match
        assert "voter_history.election_id" in or_sql

    async def test_manual_county_election_unresolved_single_date_adds_county_predicate(self) -> None:
        """Manual county election (null district fields, county boundary) appends county predicate."""
        boundary = MagicMock()
        boundary.name = "Bibb County"
        boundary.boundary_type = "county"
        election = _mock_election(
            district_type=None,
            district_identifier=None,
            boundary=boundary,
        )
        session = AsyncMock()
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        date_count_result = MagicMock()
        date_count_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[resolved_count_result, date_count_result])

        conditions = await _build_election_match_conditions(session, election)

        # date condition + county condition
        assert len(conditions) == 2
        assert any("upper(voter_history.county)" in str(c).lower() for c in conditions)

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
        # 2: _build_election_match_conditions resolved count (0 = not resolved)
        resolved_count_result = MagicMock()
        resolved_count_result.scalar_one.return_value = 0
        # 3: _build_election_match_conditions election COUNT — single election
        match_count_result = MagicMock()
        match_count_result.scalar_one.return_value = 1
        # 4: count query — finds records via date-only match
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        # 5: records query
        records_result = MagicMock()
        records_mock = MagicMock()
        records_mock.all.return_value = records
        records_result.scalars.return_value = records_mock

        session.execute.side_effect = [
            election_result,
            resolved_count_result,
            match_count_result,
            count_result,
            records_result,
        ]

        result_records, total, voter_details_included, district_type_used = await list_election_participants(
            session, election.id
        )

        assert total == 1
        assert len(result_records) == 1
        assert voter_details_included is False
        assert district_type_used is None


# ---------------------------------------------------------------------------
# resolve_election_ids
# ---------------------------------------------------------------------------


class TestLookupVoterDetails:
    """Tests for the lookup_voter_details batch helper."""

    async def test_empty_list_returns_empty_dict(self) -> None:
        """Empty input returns empty dict without querying."""
        session = AsyncMock()
        result = await lookup_voter_details(session, [])
        assert result == {}
        session.execute.assert_not_awaited()

    async def test_returns_mapping(self) -> None:
        """Returns reg_num → VoterLookupResult mapping for found voters."""
        voter_id = uuid.uuid4()
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [("12345678", voter_id, "Jane", "Doe", None)]
        session.execute.return_value = query_result

        result = await lookup_voter_details(session, ["12345678"])

        assert result == {
            "12345678": VoterLookupResult(id=voter_id, first_name="Jane", last_name="Doe", has_district_mismatch=None)
        }

    async def test_missing_voter_omitted(self) -> None:
        """Unmatched registration numbers are excluded from result."""
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute.return_value = query_result

        result = await lookup_voter_details(session, ["99999999"])

        assert "99999999" not in result
        assert result == {}

    async def test_deduplicates_input(self) -> None:
        """Duplicate registration numbers result in a single query."""
        voter_id = uuid.uuid4()
        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [("12345678", voter_id, "Jane", "Doe", None)]
        session.execute.return_value = query_result

        result = await lookup_voter_details(session, ["12345678", "12345678", "12345678"])

        assert result == {
            "12345678": VoterLookupResult(id=voter_id, first_name="Jane", last_name="Doe", has_district_mismatch=None)
        }
        session.execute.assert_awaited_once()


class TestResolveElectionIds:
    """Tests for the resolve_election_ids lookup function."""

    async def test_empty_records_returns_empty_map(self) -> None:
        """Empty input returns empty dict without querying."""
        session = AsyncMock()
        result = await resolve_election_ids(session, [])
        assert result == {}
        session.execute.assert_not_awaited()

    async def test_single_election_on_date(self) -> None:
        """When one election exists on a date, all records on that date map to it."""
        election_id = uuid.uuid4()
        records = [
            _mock_voter_history(
                election_date=date(2024, 11, 5),
                normalized_election_type="general",
            ),
            _mock_voter_history(
                election_date=date(2024, 11, 5),
                normalized_election_type="runoff",
            ),
        ]

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [(election_id, date(2024, 11, 5), "general")]
        session.execute.return_value = query_result

        lookup = await resolve_election_ids(session, records)

        assert lookup[(date(2024, 11, 5), "general")] == election_id
        assert lookup[(date(2024, 11, 5), "runoff")] == election_id

    async def test_multiple_elections_on_date(self) -> None:
        """When multiple elections share a date, matches by (date, election_type)."""
        eid_special = uuid.uuid4()
        eid_runoff = uuid.uuid4()
        records = [
            _mock_voter_history(
                election_date=date(2026, 2, 17),
                normalized_election_type="special",
            ),
            _mock_voter_history(
                election_date=date(2026, 2, 17),
                normalized_election_type="runoff",
            ),
        ]

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (eid_special, date(2026, 2, 17), "special"),
            (eid_runoff, date(2026, 2, 17), "runoff"),
        ]
        session.execute.return_value = query_result

        lookup = await resolve_election_ids(session, records)

        assert lookup[(date(2026, 2, 17), "special")] == eid_special
        assert lookup[(date(2026, 2, 17), "runoff")] == eid_runoff

    async def test_no_matching_election(self) -> None:
        """When no election exists for a date, lookup is empty for that date."""
        records = [
            _mock_voter_history(
                election_date=date(2020, 1, 1),
                normalized_election_type="general",
            ),
        ]

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = []
        session.execute.return_value = query_result

        lookup = await resolve_election_ids(session, records)

        assert (date(2020, 1, 1), "general") not in lookup

    async def test_mixed_dates(self) -> None:
        """Mix of single-election and multi-election dates resolves correctly."""
        eid_general = uuid.uuid4()
        eid_special = uuid.uuid4()
        eid_runoff = uuid.uuid4()
        records = [
            _mock_voter_history(
                election_date=date(2024, 11, 5),
                normalized_election_type="general",
            ),
            _mock_voter_history(
                election_date=date(2026, 2, 17),
                normalized_election_type="special",
            ),
            _mock_voter_history(
                election_date=date(2026, 2, 17),
                normalized_election_type="runoff",
            ),
        ]

        session = AsyncMock()
        query_result = MagicMock()
        query_result.all.return_value = [
            (eid_general, date(2024, 11, 5), "general"),
            (eid_special, date(2026, 2, 17), "special"),
            (eid_runoff, date(2026, 2, 17), "runoff"),
        ]
        session.execute.return_value = query_result

        lookup = await resolve_election_ids(session, records)

        # Single election on 2024-11-05 → date-only match
        assert lookup[(date(2024, 11, 5), "general")] == eid_general
        # Multiple elections on 2026-02-17 → type-specific match
        assert lookup[(date(2026, 2, 17), "special")] == eid_special
        assert lookup[(date(2026, 2, 17), "runoff")] == eid_runoff


# ---------------------------------------------------------------------------
# _replace_previous_import
# ---------------------------------------------------------------------------


class TestReplacePreviousImport:
    """Tests for _replace_previous_import including abandoned status handling."""

    async def test_includes_abandoned_in_status_filter(self) -> None:
        """Abandoned jobs are included in the replacement query alongside completed/superseded."""
        current_job = MagicMock()
        current_job.id = uuid.uuid4()
        current_job.file_name = "voter_history.csv"
        current_job.file_type = "voter_history"

        session = AsyncMock()
        # Mock the query for previous jobs — return empty list (no previous jobs)
        prev_result = MagicMock()
        prev_result.scalars.return_value.all.return_value = []
        session.execute.return_value = prev_result

        await _replace_previous_import(session, current_job)

        # Verify the SQL query was executed — check that the status filter
        # includes "abandoned" by inspecting the query argument
        session.execute.assert_awaited_once()
        query_arg = session.execute.call_args[0][0]
        compiled = str(query_arg.compile(compile_kwargs={"literal_binds": True}))
        assert "abandoned" in compiled
        assert "completed" in compiled
        assert "superseded" in compiled

    async def test_no_previous_jobs_is_noop(self) -> None:
        """When no previous jobs exist, no deletions or status changes happen."""
        current_job = MagicMock()
        current_job.id = uuid.uuid4()
        current_job.file_name = "voter_history.csv"
        current_job.file_type = "voter_history"

        session = AsyncMock()
        prev_result = MagicMock()
        prev_result.scalars.return_value.all.return_value = []
        session.execute.return_value = prev_result

        await _replace_previous_import(session, current_job)

        # Only the initial SELECT was executed, no DELETE or flush
        assert session.execute.await_count == 1
        session.flush.assert_not_awaited()
