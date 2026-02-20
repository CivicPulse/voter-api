"""Unit tests for meeting search service."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.meeting_search_service import MIN_QUERY_LENGTH, search_meetings


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def admin_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = "admin"
    return user


@pytest.fixture
def contributor_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = "contributor"
    return user


class TestSearchMeetingsValidation:
    async def test_short_query_raises_value_error(self, mock_session):
        with pytest.raises(ValueError, match="at least"):
            await search_meetings(mock_session, query="a")

    async def test_empty_query_raises_value_error(self, mock_session):
        with pytest.raises(ValueError, match="at least"):
            await search_meetings(mock_session, query="")

    async def test_whitespace_only_query_raises_value_error(self, mock_session):
        with pytest.raises(ValueError, match="at least"):
            await search_meetings(mock_session, query=" ")

    def test_min_query_length_constant(self):
        assert MIN_QUERY_LENGTH == 2


class TestSearchMeetingsExecution:
    async def test_returns_results_and_total(self, mock_session, admin_user):
        mock_row = {
            "agenda_item_id": uuid.uuid4(),
            "title": "Budget",
            "description_excerpt": "Annual budget...",
            "meeting_id": uuid.uuid4(),
            "meeting_date": "2024-01-15",
            "meeting_type": "regular",
            "governing_body_id": uuid.uuid4(),
            "governing_body_name": "Council",
            "match_source": "agenda_item",
            "relevance_score": 0.9,
        }

        # Mock count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        # Mock results query
        results_result = MagicMock()
        results_result.mappings.return_value.all.return_value = [mock_row]

        mock_session.execute = AsyncMock(side_effect=[count_result, results_result])

        items, total = await search_meetings(
            mock_session,
            query="budget",
            current_user=admin_user,
        )

        assert total == 1
        assert len(items) == 1
        assert items[0]["title"] == "Budget"

    async def test_empty_results(self, mock_session, admin_user):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        results_result = MagicMock()
        results_result.mappings.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, results_result])

        items, total = await search_meetings(
            mock_session,
            query="nonexistent",
            current_user=admin_user,
        )

        assert total == 0
        assert items == []

    async def test_pagination_offset(self, mock_session, admin_user):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 25

        results_result = MagicMock()
        results_result.mappings.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, results_result])

        _, total = await search_meetings(
            mock_session,
            query="test",
            page=2,
            page_size=10,
            current_user=admin_user,
        )

        assert total == 25
        # Verify execute was called twice (count + results)
        assert mock_session.execute.call_count == 2

    async def test_non_admin_visibility_filter(self, mock_session, contributor_user):
        """Non-admin users should have visibility filtering applied."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        results_result = MagicMock()
        results_result.mappings.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, results_result])

        _, total = await search_meetings(
            mock_session,
            query="test",
            current_user=contributor_user,
        )

        assert total == 0
        # The function should still execute without error
        assert mock_session.execute.call_count == 2

    async def test_no_user_context(self, mock_session):
        """Search without user context should work (admin visibility)."""
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        results_result = MagicMock()
        results_result.mappings.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[count_result, results_result])

        _, total = await search_meetings(
            mock_session,
            query="test",
        )

        assert total == 0
