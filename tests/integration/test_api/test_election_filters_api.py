"""Integration tests for election search and filter query parameters.

Tests verify that new search/filter query parameters (q, race_category, county,
election_date) are correctly passed through the route handler to the service layer,
and that validation (min/max length, enum, date format) returns 422 on bad input.
"""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.elections import elections_router

from .conftest import make_test_app


@pytest.fixture
def app(mock_session):
    return make_test_app(elections_router, mock_session)


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        follow_redirects=False,
    ) as c:
        yield c


def _patch_list_elections():
    """Patch list_elections to return empty results by default."""
    return patch(
        "voter_api.services.election_service.list_elections",
        new_callable=AsyncMock,
        return_value=([], 0),
    )


class TestElectionSearch:
    """SRCH-01: Free-text search via q parameter."""

    @pytest.mark.asyncio
    async def test_q_param_passed_to_service(self, client):
        """GET /elections?q=primary passes q='primary' to list_elections."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?q=primary")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] == "primary"

    @pytest.mark.asyncio
    async def test_q_min_length_validation(self, client):
        """GET /elections?q=a (1 char) returns 422 — min_length=2."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?q=a")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_q_max_length_validation(self, client):
        """GET /elections?q=<201 chars> returns 422 — max_length=200."""
        long_q = "a" * 201
        with _patch_list_elections():
            resp = await client.get(f"/api/v1/elections?q={long_q}")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_q_returns_200(self, client):
        """GET /elections?q=senate returns 200 with valid length."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?q=senate")
        assert resp.status_code == 200


class TestWildcardEscaping:
    """SRCH-02: Wildcard characters in q are passed through to service."""

    @pytest.mark.asyncio
    async def test_q_with_percent_passed_through(self, client):
        """GET /elections?q=100%25 (URL-encoded %) passes q='100%' to service."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?q=100%25")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] == "100%"

    @pytest.mark.asyncio
    async def test_q_with_underscore_passed_through(self, client):
        """GET /elections?q=District_1 passes q='District_1' to service."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?q=District_1")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] == "District_1"


class TestRaceCategoryFilter:
    """FILT-01: race_category enum filter."""

    @pytest.mark.asyncio
    async def test_race_category_federal(self, client):
        """GET /elections?race_category=federal passes race_category='federal'."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?race_category=federal")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["race_category"] == "federal"

    @pytest.mark.asyncio
    async def test_race_category_local(self, client):
        """GET /elections?race_category=local passes race_category='local'."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?race_category=local")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["race_category"] == "local"

    @pytest.mark.asyncio
    async def test_race_category_invalid_returns_422(self, client):
        """GET /elections?race_category=nonexistent returns 422."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?race_category=nonexistent")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_race_category_returns_200(self, client):
        """GET /elections?race_category=state_house returns 200."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?race_category=state_house")
        assert resp.status_code == 200


class TestCountyFilter:
    """FILT-02: County filter parameter."""

    @pytest.mark.asyncio
    async def test_county_param_passed_to_service(self, client):
        """GET /elections?county=Bibb passes county='Bibb' to list_elections."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?county=Bibb")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["county"] == "Bibb"

    @pytest.mark.asyncio
    async def test_county_returns_200(self, client):
        """GET /elections?county=Fulton returns 200."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?county=Fulton")
        assert resp.status_code == 200


class TestElectionDateFilter:
    """FILT-03: Exact election date filter."""

    @pytest.mark.asyncio
    async def test_election_date_param_passed(self, client):
        """GET /elections?election_date=2026-05-19 passes date(2026, 5, 19)."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?election_date=2026-05-19")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["election_date"] == date(2026, 5, 19)

    @pytest.mark.asyncio
    async def test_election_date_invalid_returns_422(self, client):
        """GET /elections?election_date=not-a-date returns 422."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?election_date=not-a-date")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_election_date_returns_200(self, client):
        """GET /elections?election_date=2026-05-19 returns 200."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections?election_date=2026-05-19")
        assert resp.status_code == 200


class TestCombinedFilters:
    """FILT-04: Multiple filters combine with AND logic."""

    @pytest.mark.asyncio
    async def test_q_and_county_combined(self, client):
        """GET /elections?q=primary&county=Bibb passes both params."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?q=primary&county=Bibb")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] == "primary"
            assert call_kwargs["county"] == "Bibb"

    @pytest.mark.asyncio
    async def test_race_category_and_date(self, client):
        """GET /elections?race_category=federal&election_date=2026-05-19 passes both."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?race_category=federal&election_date=2026-05-19")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["race_category"] == "federal"
            assert call_kwargs["election_date"] == date(2026, 5, 19)

    @pytest.mark.asyncio
    async def test_all_new_filters_combined(self, client):
        """All 4 new filters combined in a single request."""
        with _patch_list_elections() as mock_list:
            resp = await client.get(
                "/api/v1/elections?q=senate&race_category=state_senate&county=Fulton&election_date=2026-05-19"
            )
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] == "senate"
            assert call_kwargs["race_category"] == "state_senate"
            assert call_kwargs["county"] == "Fulton"
            assert call_kwargs["election_date"] == date(2026, 5, 19)


class TestBackwardCompatibility:
    """INTG-02: Existing parameters unchanged, new params default to None."""

    @pytest.mark.asyncio
    async def test_no_new_params_returns_200(self, client):
        """GET /elections with no new params returns 200."""
        with _patch_list_elections():
            resp = await client.get("/api/v1/elections")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_existing_district_filter_still_works(self, client):
        """GET /elections?district=senate passes district='senate'."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?district=senate")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["district"] == "senate"

    @pytest.mark.asyncio
    async def test_existing_date_range_still_works(self, client):
        """GET /elections?date_from=2026-01-01&date_to=2026-12-31 passes both."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections?date_from=2026-01-01&date_to=2026-12-31")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["date_from"] == date(2026, 1, 1)
            assert call_kwargs["date_to"] == date(2026, 12, 31)

    @pytest.mark.asyncio
    async def test_new_params_default_to_none(self, client):
        """GET /elections with no new params defaults q, race_category, county, election_date to None."""
        with _patch_list_elections() as mock_list:
            resp = await client.get("/api/v1/elections")
            assert resp.status_code == 200
            mock_list.assert_called_once()
            call_kwargs = mock_list.call_args.kwargs
            assert call_kwargs["q"] is None
            assert call_kwargs["race_category"] is None
            assert call_kwargs["county"] is None
            assert call_kwargs["election_date"] is None
