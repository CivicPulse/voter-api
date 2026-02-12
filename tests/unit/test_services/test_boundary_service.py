"""Tests for boundary service spatial county filter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from voter_api.services.boundary_service import (
    _county_geometry_subquery,
    find_containing_boundaries,
    list_boundaries,
)


def _compile_query(query) -> str:
    """Compile a SQLAlchemy query to a PostgreSQL SQL string for inspection."""
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _mock_session() -> AsyncMock:
    """Create a mock async session that returns empty results."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_result
    return session


class TestCountyGeometrySubquery:
    """Tests for the _county_geometry_subquery helper."""

    def test_returns_scalar_subquery(self) -> None:
        """The helper returns a scalar subquery object."""
        subq = _county_geometry_subquery("Bibb")
        # ScalarSelect is the result of .scalar_subquery()
        assert hasattr(subq, "correlate")

    def test_uses_case_insensitive_matching(self) -> None:
        """The subquery uses upper() for case-insensitive county name matching."""
        subq = _county_geometry_subquery("bibb")
        compiled = _compile_query(subq)
        assert "upper" in compiled.lower()

    def test_filters_by_county_boundary_type(self) -> None:
        """The subquery filters to boundary_type = 'county'."""
        subq = _county_geometry_subquery("Fulton")
        compiled = _compile_query(subq)
        assert "county" in compiled.lower()


class TestListBoundariesSpatialCountyFilter:
    """Tests for list_boundaries with spatial county filter."""

    @pytest.mark.asyncio
    async def test_county_filter_uses_st_intersects(self) -> None:
        """When county is provided, the query uses ST_Intersects."""
        session = _mock_session()

        await list_boundaries(session, county="Bibb")

        # At least one execute call should contain ST_Intersects
        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("st_intersects" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_without_county_no_st_intersects(self) -> None:
        """Without county param, ST_Intersects is not in the query."""
        session = _mock_session()

        await list_boundaries(session)

        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert not any("st_intersects" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_county_composes_with_boundary_type(self) -> None:
        """County and boundary_type filters can be combined."""
        session = _mock_session()

        await list_boundaries(session, county="Bibb", boundary_type="congressional")

        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        # Both filters should appear in the query
        assert any("st_intersects" in q.lower() and "congressional" in q.lower() for q in queries)


class TestFindContainingBoundariesSpatialCountyFilter:
    """Tests for find_containing_boundaries with spatial county filter."""

    @pytest.mark.asyncio
    async def test_county_filter_adds_st_intersects(self) -> None:
        """When county is provided, ST_Intersects is added alongside ST_Contains."""
        session = _mock_session()

        await find_containing_boundaries(session, 33.7, -84.4, county="Bibb")

        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "st_intersects" in compiled.lower()
        assert "st_contains" in compiled.lower()

    @pytest.mark.asyncio
    async def test_without_county_no_st_intersects(self) -> None:
        """Without county param, only ST_Contains is in the query."""
        session = _mock_session()

        await find_containing_boundaries(session, 33.7, -84.4)

        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "st_contains" in compiled.lower()
        assert "st_intersects" not in compiled.lower()
