"""Unit tests for get_filter_options service function."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

from voter_api.services.election_service import get_filter_options


def _mock_execute_results(results: list) -> AsyncMock:
    """Create a mock Result object that returns the given rows."""
    mock_result = MagicMock()
    mock_result.all.return_value = results
    mock_result.scalar_one.return_value = results[0][0] if results else 0
    return mock_result


def _make_session(side_effects: list) -> AsyncMock:
    """Create a mock AsyncSession with execute returning side_effects in order."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=side_effects)
    return session


class TestGetFilterOptions:
    """Tests for the get_filter_options service function."""

    async def test_returns_required_keys(self) -> None:
        """get_filter_options returns dict with race_categories, counties, election_dates, total_elections."""
        session = _make_session(
            [
                _mock_execute_results([]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count (scalar_one returns 0)
            ]
        )

        result = await get_filter_options(session)

        assert set(result.keys()) == {"race_categories", "counties", "election_dates", "total_elections"}

    async def test_soft_deleted_excluded(self) -> None:
        """Soft-deleted elections are excluded — verified by inspecting compiled SQL predicates."""
        from sqlalchemy.dialects import postgresql

        count_mock = _mock_execute_results([])
        count_mock.scalar_one.return_value = 1
        session = _make_session(
            [
                _mock_execute_results([("congressional",)]),  # district types
                _mock_execute_results([("FULTON",)]),  # counties
                _mock_execute_results([(date(2024, 11, 5),)]),  # dates
                count_mock,  # count
            ]
        )

        result = await get_filter_options(session)

        assert result["total_elections"] == 1

        # Every query passed to session.execute must include the soft-delete predicate.
        dialect = postgresql.dialect()
        for call in session.execute.call_args_list:
            stmt = call.args[0]
            compiled = str(stmt.compile(dialect=dialect))
            assert "deleted_at IS NULL" in compiled, f"Expected 'deleted_at IS NULL' in compiled SQL:\n{compiled}"

    async def test_counties_title_case_normalized(self) -> None:
        """Counties are title-case normalized: 'FULTON' -> 'Fulton', 'DE KALB' -> 'De Kalb'."""
        session = _make_session(
            [
                _mock_execute_results([]),  # district types
                _mock_execute_results([("DE KALB",), ("FULTON",)]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert result["counties"] == ["De Kalb", "Fulton"]

    async def test_election_dates_sorted_descending(self) -> None:
        """Election dates are sorted descending (newest first)."""
        d1 = date(2024, 5, 21)
        d2 = date(2024, 11, 5)
        session = _make_session(
            [
                _mock_execute_results([]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([(d2,), (d1,)]),  # dates already desc from query
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert result["election_dates"] == [d2, d1]

    async def test_race_categories_from_map(self) -> None:
        """Race categories derived from RACE_CATEGORY_MAP: 'congressional' -> 'federal'."""
        session = _make_session(
            [
                _mock_execute_results([("congressional",)]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert "federal" in result["race_categories"]

    async def test_null_district_type_maps_to_local(self) -> None:
        """NULL district_type maps to 'local' category."""
        session = _make_session(
            [
                _mock_execute_results([(None,)]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert "local" in result["race_categories"]

    async def test_unrecognized_district_type_maps_to_local(self) -> None:
        """Unrecognized district_type (e.g., 'county_commission') maps to 'local'."""
        session = _make_session(
            [
                _mock_execute_results([("county_commission",)]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert "local" in result["race_categories"]

    async def test_race_categories_sorted_alphabetically(self) -> None:
        """Race categories are sorted alphabetically."""
        session = _make_session(
            [
                _mock_execute_results(
                    [
                        ("state_house",),
                        ("congressional",),
                        (None,),
                    ]
                ),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert result["race_categories"] == sorted(result["race_categories"])
        assert "federal" in result["race_categories"]
        assert "local" in result["race_categories"]
        assert "state_house" in result["race_categories"]

    async def test_null_county_excluded(self) -> None:
        """NULL eligible_county values excluded from counties list."""
        session = _make_session(
            [
                _mock_execute_results([]),  # district types
                _mock_execute_results([("FULTON",)]),  # counties (already filtered by IS NOT NULL in query)
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        # NULL should not appear — the query filters it out
        assert None not in result["counties"]
        assert result["counties"] == ["Fulton"]

    async def test_empty_database_returns_empty(self) -> None:
        """Empty database (no active elections) returns empty lists and total_elections=0."""
        session = _make_session(
            [
                _mock_execute_results([]),  # district types
                _mock_execute_results([]),  # counties
                _mock_execute_results([]),  # dates
                _mock_execute_results([]),  # count
            ]
        )

        result = await get_filter_options(session)

        assert result["race_categories"] == []
        assert result["counties"] == []
        assert result["election_dates"] == []
        assert result["total_elections"] == 0
