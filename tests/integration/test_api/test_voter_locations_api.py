"""Integration tests for voter geocoded-location endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from voter_api.api.v1.voters import voters_router
from voter_api.models.geocoded_location import GeocodedLocation

from .conftest import make_test_app


@pytest.fixture
def app(mock_session: AsyncMock) -> FastAPI:
    """Minimal FastAPI app with voters router (no auth override)."""
    return make_test_app(voters_router, mock_session)


@pytest.fixture
def admin_app(mock_session: AsyncMock, mock_admin_user: MagicMock) -> FastAPI:
    """FastAPI app with admin auth."""
    return make_test_app(voters_router, mock_session, user=mock_admin_user)


@pytest.fixture
def viewer_app(mock_session: AsyncMock, mock_viewer_user: MagicMock) -> FastAPI:
    """FastAPI app with viewer auth."""
    return make_test_app(voters_router, mock_session, user=mock_viewer_user)


def _make_location(
    voter_id: uuid.UUID,
    *,
    is_primary: bool = True,
    source_type: str = "manual",
    location_id: uuid.UUID | None = None,
) -> GeocodedLocation:
    """Build a GeocodedLocation ORM object for use in mocks."""
    return GeocodedLocation(
        id=location_id or uuid.uuid4(),
        voter_id=voter_id,
        latitude=33.749,
        longitude=-84.388,
        confidence_score=None,
        source_type=source_type,
        is_primary=is_primary,
        input_address=None,
        geocoded_at=datetime.now(UTC),
    )


class TestManualGeocodedLocationEndpoint:
    """Tests for POST /api/v1/voters/{voter_id}/geocoded-locations/manual."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        voter_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/voters/{voter_id}/geocoded-locations/manual",
            json={"latitude": 33.749, "longitude": -84.388, "source_type": "manual"},
        )
        assert resp.status_code == 401

    async def test_viewer_can_add_manual_location(self, viewer_client) -> None:
        """Any authenticated user (including viewer) can add a manual location (auth required, no role restriction)."""
        voter_id = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
        mock_location = _make_location(voter_id)

        with patch(
            "voter_api.api.v1.voters.add_manual_location",
            new_callable=AsyncMock,
            return_value=mock_location,
        ):
            resp = await viewer_client.post(
                f"/api/v1/voters/{voter_id}/geocoded-locations/manual",
                json={"latitude": 33.749, "longitude": -84.388, "source_type": "manual"},
            )

        assert resp.status_code == 201

    async def test_returns_location_fields(self, admin_client) -> None:
        """Returns 201 with all expected GeocodedLocationResponse fields."""
        voter_id = uuid.UUID("cccccccc-0000-0000-0000-000000000002")
        location_id = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
        mock_location = _make_location(voter_id, location_id=location_id)

        with patch(
            "voter_api.api.v1.voters.add_manual_location",
            new_callable=AsyncMock,
            return_value=mock_location,
        ):
            resp = await admin_client.post(
                f"/api/v1/voters/{voter_id}/geocoded-locations/manual",
                json={"latitude": 33.749, "longitude": -84.388, "source_type": "manual"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == str(location_id)
        assert data["voter_id"] == str(voter_id)
        assert data["latitude"] == pytest.approx(33.749)
        assert data["longitude"] == pytest.approx(-84.388)
        assert data["source_type"] == "manual"
        assert data["is_primary"] is True

    async def test_set_as_primary_flag_forwarded(self, admin_client) -> None:
        """set_as_primary=True is forwarded to the service."""
        voter_id = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
        mock_location = _make_location(voter_id, is_primary=True)

        with patch(
            "voter_api.api.v1.voters.add_manual_location",
            new_callable=AsyncMock,
            return_value=mock_location,
        ) as mock_add:
            resp = await admin_client.post(
                f"/api/v1/voters/{voter_id}/geocoded-locations/manual",
                json={
                    "latitude": 33.749,
                    "longitude": -84.388,
                    "source_type": "field-survey",
                    "set_as_primary": True,
                },
            )

        assert resp.status_code == 201
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["set_as_primary"] is True
        assert call_kwargs["source_type"] == "field-survey"

    async def test_invalid_source_type_returns_422(self, admin_client) -> None:
        """Invalid source_type (not manual/field-survey) returns 422."""
        voter_id = uuid.uuid4()
        resp = await admin_client.post(
            f"/api/v1/voters/{voter_id}/geocoded-locations/manual",
            json={"latitude": 33.749, "longitude": -84.388, "source_type": "census"},
        )
        assert resp.status_code == 422


class TestSetPrimaryGeocodedLocationEndpoint:
    """Tests for PUT /api/v1/voters/{voter_id}/geocoded-locations/{location_id}/set-primary."""

    async def test_requires_auth_returns_401(self, client) -> None:
        """Unauthenticated request returns 401."""
        voter_id = uuid.uuid4()
        location_id = uuid.uuid4()
        resp = await client.put(f"/api/v1/voters/{voter_id}/geocoded-locations/{location_id}/set-primary")
        assert resp.status_code == 401

    async def test_viewer_cannot_set_primary_returns_403(self, viewer_client) -> None:
        """Viewer role cannot set primary (admin-only endpoint returns 403)."""
        voter_id = uuid.uuid4()
        location_id = uuid.uuid4()
        resp = await viewer_client.put(f"/api/v1/voters/{voter_id}/geocoded-locations/{location_id}/set-primary")
        assert resp.status_code == 403

    async def test_unknown_location_returns_404(self, admin_client) -> None:
        """Non-existent location ID returns 404."""
        voter_id = uuid.uuid4()
        location_id = uuid.uuid4()
        with patch(
            "voter_api.api.v1.voters.set_primary_location",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.put(f"/api/v1/voters/{voter_id}/geocoded-locations/{location_id}/set-primary")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    async def test_admin_sets_primary_returns_200(self, admin_client) -> None:
        """Admin can set a location as primary; returns 200 with location fields."""
        voter_id = uuid.UUID("cccccccc-0000-0000-0000-000000000004")
        location_id = uuid.UUID("dddddddd-0000-0000-0000-000000000002")
        mock_location = _make_location(voter_id, is_primary=True, location_id=location_id)

        with patch(
            "voter_api.api.v1.voters.set_primary_location",
            new_callable=AsyncMock,
            return_value=mock_location,
        ):
            resp = await admin_client.put(f"/api/v1/voters/{voter_id}/geocoded-locations/{location_id}/set-primary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(location_id)
        assert data["voter_id"] == str(voter_id)
        assert data["is_primary"] is True
