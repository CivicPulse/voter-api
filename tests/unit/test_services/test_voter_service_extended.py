"""Extended tests for voter_service — covering search_voters and get_voter_detail."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from voter_api.services.voter_service import get_voter_detail, get_voter_filter_options, search_voters


def _compile_query(stmt: object) -> str:
    """Compile a SQLAlchemy statement to a SQL string with literal binds for inspection."""
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _mock_voter(**overrides: object) -> MagicMock:
    """Create a mock Voter."""
    voter = MagicMock()
    voter.id = uuid.uuid4()
    voter.voter_registration_number = "12345678"
    voter.last_name = "SMITH"
    voter.first_name = "JOHN"
    voter.county = "FULTON"
    for key, value in overrides.items():
        setattr(voter, key, value)
    return voter


class TestSearchVoters:
    """Tests for search_voters with mocked session."""

    @pytest.mark.asyncio
    async def test_returns_voters_and_count(self) -> None:
        session = AsyncMock()
        voters = [_mock_voter(), _mock_voter()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = voters
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session)
        assert total == 2
        assert len(result_voters) == 2

    @pytest.mark.asyncio
    async def test_filter_by_registration_number(self) -> None:
        session = AsyncMock()
        voter = _mock_voter()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [voter]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, voter_registration_number="12345678")
        assert total == 1

    @pytest.mark.asyncio
    async def test_filter_by_name(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, first_name="JOHN", last_name="SMITH")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_county(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, county="FULTON")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_city_and_zipcode(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, residence_city="ATLANTA", residence_zipcode="30301")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, status="ACTIVE")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_districts(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(
            session,
            congressional_district="05",
            state_senate_district="34",
            state_house_district="55",
            county_precinct="SS01",
        )
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_import_presence(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, present_in_latest_import=True)
        assert total == 0

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 100
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter()] * 10
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, page=5, page_size=10)
        assert total == 100
        assert len(result_voters) == 10

    @pytest.mark.asyncio
    async def test_all_filters_combined(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(
            session,
            voter_registration_number="12345678",
            first_name="JOHN",
            last_name="SMITH",
            county="FULTON",
            residence_city="ATLANTA",
            residence_zipcode="30301",
            status="ACTIVE",
            congressional_district="05",
            state_senate_district="34",
            state_house_district="55",
            county_precinct="SS01",
            present_in_latest_import=True,
        )
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_q_single_word(self) -> None:
        """Test combined name search with single word."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter()]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="Smith")
        assert total == 1

        # Verify the count query actually contains ILIKE conditions for all 3 name fields
        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        assert "ILIKE" in compiled
        assert "%Smith%" in compiled
        # One word generates OR across 3 name fields
        assert compiled.count("ILIKE") == 3

    @pytest.mark.asyncio
    async def test_filter_by_q_multiple_words(self) -> None:
        """Test combined name search with multiple words — each token must appear."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter()]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="John Smith")
        assert total == 1

        # Both tokens must appear in the query (AND across words, OR across fields)
        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        assert "%John%" in compiled
        assert "%Smith%" in compiled
        # Two words × 3 name fields = 6 ILIKE conditions
        assert compiled.count("ILIKE") == 6

    @pytest.mark.asyncio
    async def test_filter_by_q_with_other_filters(self) -> None:
        """Test combined name search works alongside other filters."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter()]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="Smith", county="FULTON")
        assert total == 1

        # Verify both the ILIKE name filter and the county equality filter are present
        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        assert "%Smith%" in compiled
        assert "ILIKE" in compiled
        assert "FULTON" in compiled

    @pytest.mark.asyncio
    async def test_filter_by_q_empty_string_ignored(self) -> None:
        """Test that empty q parameter adds no ILIKE conditions."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter(), _mock_voter()]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="")
        assert total == 2

        # No ILIKE conditions should be generated for an empty q
        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        assert "ILIKE" not in compiled

    @pytest.mark.asyncio
    async def test_filter_by_q_whitespace_only_ignored(self) -> None:
        """Test that whitespace-only q parameter adds no ILIKE conditions."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_voter(), _mock_voter()]
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="   ")
        assert total == 2

        # Whitespace-only input produces no tokens, so no ILIKE conditions
        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        assert "ILIKE" not in compiled

    @pytest.mark.asyncio
    async def test_filter_by_q_escapes_sql_wildcards(self) -> None:
        """Test that SQL wildcard characters % and _ in q are escaped as literals."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="100%")
        assert total == 0

        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        # The % must be escaped so it appears as \% in the pattern, not as a wildcard
        # The compiled SQL should contain the escaped form, not the raw user input as a wildcard
        assert "ILIKE" in compiled
        assert r"\%" in compiled  # escaped percent sign
        # Must not contain the double-wildcard pattern that a raw % would produce
        assert "100%%" not in compiled

    @pytest.mark.asyncio
    async def test_filter_by_q_escapes_underscore_wildcard(self) -> None:
        """Test that underscore _ in q is escaped so it matches literally, not any character."""
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        result_voters, total = await search_voters(session, q="_mith")
        assert total == 0

        count_stmt = session.execute.call_args_list[0][0][0]
        compiled = _compile_query(count_stmt)
        # The _ must be escaped so it is treated as a literal underscore, not a single-char wildcard
        assert "ILIKE" in compiled
        assert r"\_" in compiled  # escaped underscore


class TestGetVoterDetail:
    """Tests for get_voter_detail."""

    @pytest.mark.asyncio
    async def test_returns_voter_when_found(self) -> None:
        voter = _mock_voter()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = voter
        session.execute.return_value = result

        found = await get_voter_detail(session, voter.id)
        assert found is voter

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_voter_detail(session, uuid.uuid4())
        assert found is None


class TestGetVoterFilterOptions:
    """Tests for get_voter_filter_options."""

    def _make_execute_result(self, rows: list[str]) -> MagicMock:
        result = MagicMock()
        result.all.return_value = [(v,) for v in rows]
        return result

    @pytest.mark.asyncio
    async def test_returns_all_filter_keys(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [
            self._make_execute_result(["Active", "Inactive"]),
            self._make_execute_result(["Cobb", "Fulton"]),
            self._make_execute_result(["05", "06"]),
            self._make_execute_result(["34", "35"]),
            self._make_execute_result(["55", "56"]),
        ]

        options = await get_voter_filter_options(session)

        assert set(options.keys()) == {
            "statuses",
            "counties",
            "congressional_districts",
            "state_senate_districts",
            "state_house_districts",
        }

    @pytest.mark.asyncio
    async def test_returns_correct_values(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [
            self._make_execute_result(["Active", "Inactive"]),
            self._make_execute_result(["Cobb", "Fulton"]),
            self._make_execute_result(["05", "06"]),
            self._make_execute_result(["34"]),
            self._make_execute_result(["55"]),
        ]

        options = await get_voter_filter_options(session)

        assert options["statuses"] == ["Active", "Inactive"]
        assert options["counties"] == ["Cobb", "Fulton"]
        assert options["congressional_districts"] == ["05", "06"]
        assert options["state_senate_districts"] == ["34"]
        assert options["state_house_districts"] == ["55"]

    @pytest.mark.asyncio
    async def test_returns_empty_lists_when_no_data(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
        ]

        options = await get_voter_filter_options(session)

        assert options["statuses"] == []
        assert options["counties"] == []
        assert options["congressional_districts"] == []
        assert options["state_senate_districts"] == []
        assert options["state_house_districts"] == []

    @pytest.mark.asyncio
    async def test_executes_five_queries(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
            self._make_execute_result([]),
        ]

        await get_voter_filter_options(session)

        assert session.execute.call_count == 5
