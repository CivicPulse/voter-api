"""Integration tests for voter district check and mismatch filter."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from voter_api.api.v1.voters import voters_router

from .conftest import make_test_app


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Minimal FastAPI app with voters router (no auth override)."""
    return make_test_app(voters_router, mock_session)


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    return make_test_app(voters_router, mock_session, user=mock_admin_user)


class TestDistrictCheckEndpoint:
    """Tests for GET /api/v1/voters/{voter_id}/district-check."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        voter_id = uuid.uuid4()
        resp = await client.get(f"/api/v1/voters/{voter_id}/district-check")
        assert resp.status_code == 401

    async def test_voter_not_found_returns_404(self, admin_client) -> None:
        """Unknown voter returns 404."""
        voter_id = uuid.uuid4()
        with patch(
            "voter_api.api.v1.voters.check_voter_districts",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/voters/{voter_id}/district-check")
        assert resp.status_code == 404

    async def test_happy_path_returns_district_check(self, admin_client) -> None:
        """Valid voter returns district check response."""
        voter_id = uuid.uuid4()
        mock_result = {
            "voter_id": voter_id,
            "match_status": "mismatch-district",
            "geocoded_point": {
                "latitude": 32.8407,
                "longitude": -83.6324,
                "source_type": "census",
                "confidence_score": 100.0,
            },
            "registered_boundaries": {
                "congressional": "8",
                "county_commission": "1",
            },
            "determined_boundaries": {
                "congressional": "8",
                "county_commission": "5",
            },
            "comparisons": [
                {
                    "boundary_type": "congressional",
                    "registered_value": "8",
                    "determined_value": "8",
                    "status": "match",
                },
                {
                    "boundary_type": "county_commission",
                    "registered_value": "1",
                    "determined_value": "5",
                    "status": "mismatch",
                },
            ],
            "mismatch_count": 1,
            "checked_at": datetime.now(UTC).isoformat(),
        }

        with patch(
            "voter_api.api.v1.voters.check_voter_districts",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.get(f"/api/v1/voters/{voter_id}/district-check")

        assert resp.status_code == 200
        body = resp.json()
        assert body["match_status"] == "mismatch-district"
        assert body["mismatch_count"] == 1
        assert len(body["comparisons"]) == 2
        assert body["geocoded_point"]["latitude"] == pytest.approx(32.8407)

    async def test_not_geocoded_response(self, admin_client) -> None:
        """Voter without geocoded location returns not-geocoded status."""
        voter_id = uuid.uuid4()
        mock_result = {
            "voter_id": voter_id,
            "match_status": "not-geocoded",
            "geocoded_point": None,
            "registered_boundaries": {"congressional": "8"},
            "determined_boundaries": {},
            "comparisons": [],
            "mismatch_count": 0,
            "checked_at": datetime.now(UTC).isoformat(),
        }

        with patch(
            "voter_api.api.v1.voters.check_voter_districts",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await admin_client.get(f"/api/v1/voters/{voter_id}/district-check")

        assert resp.status_code == 200
        body = resp.json()
        assert body["match_status"] == "not-geocoded"
        assert body["geocoded_point"] is None
        assert body["comparisons"] == []


class TestDistrictMismatchFilter:
    """Tests for has_district_mismatch query parameter on search endpoint."""

    async def test_filter_accepted_true(self, admin_client) -> None:
        """Search endpoint accepts has_district_mismatch=true."""
        with patch(
            "voter_api.api.v1.voters.search_voters",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_search:
            resp = await admin_client.get("/api/v1/voters?has_district_mismatch=true")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["pagination"]["total"] == 0
        # Verify the filter was passed through
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["has_district_mismatch"] is True

    async def test_filter_accepted_false(self, admin_client) -> None:
        """Search endpoint accepts has_district_mismatch=false."""
        with patch(
            "voter_api.api.v1.voters.search_voters",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_search:
            resp = await admin_client.get("/api/v1/voters?has_district_mismatch=false")

        assert resp.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["has_district_mismatch"] is False

    async def test_filter_omitted_passes_none(self, admin_client) -> None:
        """Omitting has_district_mismatch passes None to service."""
        with patch(
            "voter_api.api.v1.voters.search_voters",
            new_callable=AsyncMock,
            return_value=([], 0),
        ) as mock_search:
            resp = await admin_client.get("/api/v1/voters")

        assert resp.status_code == 200
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args.kwargs
        assert call_kwargs["has_district_mismatch"] is None
