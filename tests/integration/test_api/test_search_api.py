"""Integration tests for meeting search API."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

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


def _make_app(user: MagicMock) -> FastAPI:
    app = FastAPI()
    app.include_router(meetings_router, prefix="/api/v1")
    app.dependency_overrides[get_async_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class TestSearchEndpoint:
    async def test_search_returns_results(self):
        app = _make_app(_mock_user())
        mock_results = [
            {
                "agenda_item_id": uuid.uuid4(),
                "title": "Budget Discussion",
                "description_excerpt": "Annual budget review...",
                "meeting_id": uuid.uuid4(),
                "meeting_date": datetime.now(UTC),
                "meeting_type": "regular",
                "governing_body_id": uuid.uuid4(),
                "governing_body_name": "City Council",
                "match_source": "agenda_item",
                "relevance_score": 0.85,
            }
        ]

        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            return_value=(mock_results, 1),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/meetings/search", params={"q": "budget"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Budget Discussion"
        assert data["pagination"]["total"] == 1

    async def test_search_empty_results(self):
        app = _make_app(_mock_user())
        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/meetings/search", params={"q": "nonexistent"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0

    async def test_search_short_query_rejected(self):
        """Query shorter than 2 characters should be rejected by FastAPI validation."""
        app = _make_app(_mock_user())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/meetings/search", params={"q": "a"})

        assert resp.status_code == 422

    async def test_search_missing_query_rejected(self):
        """Missing query parameter should return 422."""
        app = _make_app(_mock_user())
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/meetings/search")

        assert resp.status_code == 422

    async def test_search_pagination(self):
        app = _make_app(_mock_user())
        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            return_value=([], 50),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(
                    "/api/v1/meetings/search",
                    params={"q": "test", "page": 2, "page_size": 10},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total"] == 50
        assert data["pagination"]["total_pages"] == 5

    async def test_search_attachment_match(self):
        app = _make_app(_mock_user())
        mock_results = [
            {
                "agenda_item_id": uuid.uuid4(),
                "title": "minutes.pdf",
                "description_excerpt": None,
                "meeting_id": uuid.uuid4(),
                "meeting_date": datetime.now(UTC),
                "meeting_type": "regular",
                "governing_body_id": uuid.uuid4(),
                "governing_body_name": "Board",
                "match_source": "attachment_filename",
                "relevance_score": 0.1,
            }
        ]

        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            return_value=(mock_results, 1),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/meetings/search", params={"q": "minutes"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["match_source"] == "attachment_filename"

    async def test_search_service_error_returns_422(self):
        app = _make_app(_mock_user())
        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            side_effect=ValueError("Search query must be at least 2 characters"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/meetings/search", params={"q": "ab"})

        assert resp.status_code == 422

    async def test_search_does_not_conflict_with_meeting_id_route(self):
        """The /search route should not be interpreted as a meeting ID."""
        app = _make_app(_mock_user())
        with patch(
            "voter_api.api.v1.meetings.search_meetings",
            new_callable=AsyncMock,
            return_value=([], 0),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/meetings/search", params={"q": "test"})

        assert resp.status_code == 200
