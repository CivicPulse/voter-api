"""Extended tests for voter_service — covering search_voters and get_voter_detail."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.voter_service import get_voter_detail, search_voters


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
