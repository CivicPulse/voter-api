"""Tests for boundary service hybrid county filter."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from voter_api.services.boundary_service import (
    _build_county_filter,
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
        subq = _county_geometry_subquery("Bibb")
        assert hasattr(subq, "correlate")

    def test_uses_case_insensitive_matching(self) -> None:
        subq = _county_geometry_subquery("bibb")
        compiled = _compile_query(subq)
        assert "upper" in compiled.lower()

    def test_filters_by_county_boundary_type(self) -> None:
        subq = _county_geometry_subquery("Fulton")
        compiled = _compile_query(subq)
        assert "county" in compiled.lower()


class TestBuildCountyFilter:
    """Tests for the _build_county_filter hybrid approach."""

    def test_filter_includes_relation_table_match(self) -> None:
        """Filter should include EXISTS against county_districts table."""
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        assert "county_districts" in compiled.lower()

    def test_filter_includes_direct_column_match(self) -> None:
        """Filter should check Boundary.county column."""
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        # Should have upper(boundaries.county) = upper('Bibb')
        assert "boundaries.county" in compiled.lower()

    def test_filter_includes_county_self_match(self) -> None:
        """Filter should match the county boundary itself by name."""
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        assert "boundaries.name" in compiled.lower()

    def test_filter_includes_spatial_fallback(self) -> None:
        """Filter should include ST_Intersects as spatial fallback."""
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        assert "st_intersects" in compiled.lower()

    def test_filter_does_not_use_centroid(self) -> None:
        """The new filter should NOT use the old centroid approach."""
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        assert "st_centroid" not in compiled.lower()

    def test_spatial_fallback_uses_per_boundary_not_exists(self) -> None:
        """Spatial fallback should check NOT EXISTS per boundary, not globally per type.

        Ensures boundaries whose identifier doesn't match county_districts
        still fall through to the ST_Intersects spatial check.
        """
        f = _build_county_filter("Bibb")
        compiled = _compile_query(f)
        # The NOT EXISTS in the spatial fallback should reference
        # district_identifier (per-boundary check), not just boundary_type
        lower = compiled.lower()
        not_exists_idx = lower.rfind("not (exists")
        assert not_exists_idx != -1, "Should have a NOT EXISTS clause for spatial fallback"
        not_exists_clause = lower[not_exists_idx:]
        assert "district_identifier" in not_exists_clause
        assert "county_name" in not_exists_clause

    def test_filter_uses_case_insensitive_matching(self) -> None:
        f = _build_county_filter("bibb")
        compiled = _compile_query(f)
        assert "upper" in compiled.lower()


class TestListBoundariesHybridCountyFilter:
    """Tests for list_boundaries with hybrid county filter."""

    @pytest.mark.asyncio
    async def test_county_filter_uses_hybrid_approach(self) -> None:
        """When county is provided, the query uses the hybrid filter."""
        session = _mock_session()

        await list_boundaries(session, county="Bibb")

        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        # Should include county_districts table reference
        assert any("county_districts" in q.lower() for q in queries)
        # Should include ST_Intersects for spatial fallback
        assert any("st_intersects" in q.lower() for q in queries)
        # Should NOT use centroid approach
        assert not any("st_centroid" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_without_county_no_county_filter(self) -> None:
        """Without county param, no county filter is in the query."""
        session = _mock_session()

        await list_boundaries(session)

        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert not any("county_districts" in q.lower() for q in queries)
        assert not any("st_intersects" in q.lower() for q in queries)

    @pytest.mark.asyncio
    async def test_county_composes_with_boundary_type(self) -> None:
        """County and boundary_type filters can be combined."""
        session = _mock_session()

        await list_boundaries(session, county="Bibb", boundary_type="congressional")

        calls = session.execute.call_args_list
        queries = [_compile_query(call[0][0]) for call in calls]
        assert any("county_districts" in q.lower() and "congressional" in q.lower() for q in queries)


class TestFindContainingBoundariesHybridCountyFilter:
    """Tests for find_containing_boundaries with hybrid county filter."""

    @pytest.mark.asyncio
    async def test_county_filter_uses_hybrid_approach(self) -> None:
        """When county is provided, the hybrid filter is used alongside ST_Contains."""
        session = _mock_session()

        await find_containing_boundaries(session, 33.7, -84.4, county="Bibb")

        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "county_districts" in compiled.lower()
        assert "st_contains" in compiled.lower()
        assert "st_centroid" not in compiled.lower()

    @pytest.mark.asyncio
    async def test_without_county_no_county_filter(self) -> None:
        """Without county param, only ST_Contains is in the query."""
        session = _mock_session()

        await find_containing_boundaries(session, 33.7, -84.4)

        call = session.execute.call_args
        compiled = _compile_query(call[0][0])
        assert "st_contains" in compiled.lower()
        assert "county_districts" not in compiled.lower()
