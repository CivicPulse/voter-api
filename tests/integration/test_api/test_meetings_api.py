"""Integration tests for meetings API endpoints."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from voter_api.api.v1.meetings import meetings_router
from voter_api.core.dependencies import get_async_session, get_current_user


def _mock_user(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.username = f"test{role}"
    user.role = role
    user.is_active = True
    return user


def _mock_governing_body() -> MagicMock:
    gb = MagicMock()
    gb.id = uuid.uuid4()
    gb.name = "Fulton County Commission"
    return gb


def _mock_meeting(**overrides) -> MagicMock:
    gb = _mock_governing_body()
    defaults = {
        "id": uuid.uuid4(),
        "governing_body_id": gb.id,
        "governing_body_name": gb.name,
        "meeting_date": datetime(2026, 3, 15, 18, 0, 0, tzinfo=UTC),
        "location": "City Hall",
        "meeting_type": "regular",
        "status": "scheduled",
        "external_source_url": None,
        "approval_status": "approved",
        "submitted_by": uuid.uuid4(),
        "approved_by": None,
        "approved_at": None,
        "rejection_reason": None,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "governing_body": gb,
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


@pytest.fixture
def admin_user() -> MagicMock:
    return _mock_user("admin")


@pytest.fixture
def viewer_user() -> MagicMock:
    return _mock_user("viewer")


@pytest.fixture
def contributor_user() -> MagicMock:
    return _mock_user("contributor")


def _make_app(user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(meetings_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.fixture
async def admin_client(admin_user: MagicMock) -> AsyncClient:
    transport = ASGITransport(app=_make_app(admin_user))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


@pytest.fixture
async def viewer_client(viewer_user: MagicMock) -> AsyncClient:
    transport = ASGITransport(app=_make_app(viewer_user))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


@pytest.fixture
async def contributor_client(contributor_user: MagicMock) -> AsyncClient:
    transport = ASGITransport(app=_make_app(contributor_user))
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


class TestListMeetings:
    @pytest.mark.asyncio
    async def test_returns_paginated(self, admin_client: AsyncClient) -> None:
        meetings = [_mock_meeting()]
        with patch(
            "voter_api.api.v1.meetings.list_meetings",
            new_callable=AsyncMock,
            return_value=(meetings, 1),
        ):
            resp = await admin_client.get("/api/v1/meetings")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        assert data["pagination"]["total"] == 1

    @pytest.mark.asyncio
    async def test_viewer_can_list(self, viewer_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.meetings.list_meetings",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            resp = await viewer_client.get("/api/v1/meetings")
        assert resp.status_code == 200


class TestCreateMeeting:
    @pytest.mark.asyncio
    async def test_admin_creates(self, admin_client: AsyncClient) -> None:
        meeting = _mock_meeting()
        with (
            patch(
                "voter_api.api.v1.meetings.create_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            resp = await admin_client.post(
                "/api/v1/meetings",
                json={
                    "governing_body_id": str(meeting.governing_body_id),
                    "meeting_date": "2026-03-15T18:00:00Z",
                    "meeting_type": "regular",
                    "status": "scheduled",
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_contributor_creates(self, contributor_client: AsyncClient) -> None:
        meeting = _mock_meeting(approval_status="pending")
        with (
            patch(
                "voter_api.api.v1.meetings.create_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            resp = await contributor_client.post(
                "/api/v1/meetings",
                json={
                    "governing_body_id": str(meeting.governing_body_id),
                    "meeting_date": "2026-03-15T18:00:00Z",
                    "meeting_type": "regular",
                    "status": "scheduled",
                },
            )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(
            "/api/v1/meetings",
            json={
                "governing_body_id": str(uuid.uuid4()),
                "meeting_date": "2026-03-15T18:00:00Z",
                "meeting_type": "regular",
                "status": "scheduled",
            },
        )
        assert resp.status_code == 403


class TestGetMeeting:
    @pytest.mark.asyncio
    async def test_returns_detail(self, admin_client: AsyncClient) -> None:
        meeting = _mock_meeting()
        with (
            patch(
                "voter_api.api.v1.meetings.get_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(3, 2, 1),
            ),
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{meeting.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agenda_item_count"] == 3
        assert data["attachment_count"] == 2
        assert data["video_embed_count"] == 1

    @pytest.mark.asyncio
    async def test_not_found(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.meetings.get_meeting",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await admin_client.get(f"/api/v1/meetings/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpdateMeeting:
    @pytest.mark.asyncio
    async def test_admin_updates(self, admin_client: AsyncClient) -> None:
        meeting = _mock_meeting(status="cancelled")
        with (
            patch(
                "voter_api.api.v1.meetings.update_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            resp = await admin_client.patch(
                f"/api/v1/meetings/{meeting.id}",
                json={"status": "cancelled"},
            )
        assert resp.status_code == 200


class TestDeleteMeeting:
    @pytest.mark.asyncio
    async def test_admin_deletes(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.meetings.delete_meeting",
            new_callable=AsyncMock,
        ):
            resp = await admin_client.delete(f"/api/v1/meetings/{uuid.uuid4()}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.delete(f"/api/v1/meetings/{uuid.uuid4()}")
        assert resp.status_code == 403


class TestApproveMeeting:
    @pytest.mark.asyncio
    async def test_admin_approves(self, admin_client: AsyncClient) -> None:
        meeting = _mock_meeting(approval_status="approved")
        with (
            patch(
                "voter_api.api.v1.meetings.approve_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            resp = await admin_client.post(f"/api/v1/meetings/{meeting.id}/approve")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_pending_returns_409(self, admin_client: AsyncClient) -> None:
        with patch(
            "voter_api.api.v1.meetings.approve_meeting",
            new_callable=AsyncMock,
            side_effect=ValueError("Meeting is not in pending status"),
        ):
            resp = await admin_client.post(f"/api/v1/meetings/{uuid.uuid4()}/approve")
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_viewer_cannot_approve(self, viewer_client: AsyncClient) -> None:
        resp = await viewer_client.post(f"/api/v1/meetings/{uuid.uuid4()}/approve")
        assert resp.status_code == 403


class TestRejectMeeting:
    @pytest.mark.asyncio
    async def test_admin_rejects(self, admin_client: AsyncClient) -> None:
        meeting = _mock_meeting(approval_status="rejected", rejection_reason="Duplicate")
        with (
            patch(
                "voter_api.api.v1.meetings.reject_meeting",
                new_callable=AsyncMock,
                return_value=meeting,
            ),
            patch(
                "voter_api.api.v1.meetings.get_child_counts",
                new_callable=AsyncMock,
                return_value=(0, 0, 0),
            ),
        ):
            resp = await admin_client.post(
                f"/api/v1/meetings/{meeting.id}/reject",
                json={"reason": "Duplicate entry"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_missing_reason_returns_422(self, admin_client: AsyncClient) -> None:
        resp = await admin_client.post(
            f"/api/v1/meetings/{uuid.uuid4()}/reject",
            json={},
        )
        assert resp.status_code == 422
