"""Unit tests for governing body service layer."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from voter_api.services.governing_body_service import (
    create_body,
    delete_body,
    get_body,
    get_meeting_count,
    list_bodies,
    update_body,
)


def _mock_session(scalar_one_value=0, scalar_one_or_none_value=None, scalars_all_value=None) -> AsyncMock:
    """Create a mock async session with configurable return values."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = scalar_one_value
    mock_result.scalar_one_or_none.return_value = scalar_one_or_none_value
    mock_result.scalars.return_value.all.return_value = scalars_all_value or []
    session.execute.return_value = mock_result
    return session


def _mock_body(**overrides) -> MagicMock:
    """Create a mock GoverningBody."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Fulton County Commission",
        "type_id": uuid.uuid4(),
        "jurisdiction": "Fulton County",
        "description": None,
        "website_url": None,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestListBodies:
    """Tests for list_bodies query building."""

    @pytest.mark.asyncio
    async def test_no_filters(self) -> None:
        """Without filters, returns all active bodies."""
        session = _mock_session()
        bodies, total = await list_bodies(session)
        assert bodies == []
        assert total == 0
        assert session.execute.call_count == 2  # count + data

    @pytest.mark.asyncio
    async def test_type_id_filter(self) -> None:
        """Filters by type_id when provided."""
        session = _mock_session()
        type_id = uuid.uuid4()
        await list_bodies(session, type_id=type_id)
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_jurisdiction_filter(self) -> None:
        """Filters by jurisdiction (partial match)."""
        session = _mock_session()
        await list_bodies(session, jurisdiction="Fulton")
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        """Pagination applies correct offset and limit."""
        session = _mock_session(scalar_one_value=50)
        bodies, total = await list_bodies(session, page=3, page_size=10)
        assert total == 50


class TestGetBody:
    """Tests for get_body."""

    @pytest.mark.asyncio
    async def test_found(self) -> None:
        """Returns body when found."""
        body = _mock_body()
        session = _mock_session(scalar_one_or_none_value=body)
        result = await get_body(session, body.id)
        assert result == body

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        """Returns None when not found."""
        session = _mock_session()
        result = await get_body(session, uuid.uuid4())
        assert result is None


class TestGetMeetingCount:
    """Tests for get_meeting_count."""

    @pytest.mark.asyncio
    async def test_returns_count(self) -> None:
        """Returns the count of active meetings."""
        session = _mock_session(scalar_one_value=5)
        count = await get_meeting_count(session, uuid.uuid4())
        assert count == 5


class TestCreateBody:
    """Tests for create_body."""

    @pytest.mark.asyncio
    async def test_creates_body(self) -> None:
        """Successfully creates a governing body."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        await create_body(
            session,
            name="Test Body",
            type_id=uuid.uuid4(),
            jurisdiction="Test County",
        )
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_raises_value_error(self) -> None:
        """Duplicate name+jurisdiction raises ValueError."""
        session = AsyncMock()
        session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        session.rollback = AsyncMock()
        with pytest.raises(ValueError, match="already exists"):
            await create_body(
                session,
                name="Dupe Body",
                type_id=uuid.uuid4(),
                jurisdiction="Dupe County",
            )


class TestUpdateBody:
    """Tests for update_body."""

    @pytest.mark.asyncio
    async def test_updates_allowed_fields(self) -> None:
        """Updates only allowlisted fields."""
        body = _mock_body()
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = body
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        result = await update_body(session, body.id, data={"name": "New Name"})
        assert result.name == "New Name"

    @pytest.mark.asyncio
    async def test_ignores_non_updatable_fields(self) -> None:
        """Fields not in _UPDATABLE_FIELDS are ignored."""
        body = _mock_body()
        original_id = body.id
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = body
        session.execute.return_value = mock_result
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        await update_body(session, body.id, data={"id": uuid.uuid4(), "deleted_at": datetime.now(UTC)})
        assert body.id == original_id

    @pytest.mark.asyncio
    async def test_not_found_raises_value_error(self) -> None:
        """Non-existent body raises ValueError."""
        session = _mock_session()
        with pytest.raises(ValueError, match="not found"):
            await update_body(session, uuid.uuid4(), data={"name": "New"})


class TestDeleteBody:
    """Tests for delete_body."""

    @pytest.mark.asyncio
    async def test_soft_deletes_body(self) -> None:
        """Sets deleted_at on the body."""
        body = _mock_body()
        # First call for get_body, second for get_meeting_count
        session = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = body
            else:
                result.scalar_one.return_value = 0
            return result

        session.execute = mock_execute
        session.commit = AsyncMock()
        await delete_body(session, body.id)
        assert body.deleted_at is not None

    @pytest.mark.asyncio
    async def test_refuses_with_active_meetings(self) -> None:
        """Refuses deletion when active meetings exist."""
        body = _mock_body()
        session = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = body
            else:
                result.scalar_one.return_value = 3  # active meetings
            return result

        session.execute = mock_execute
        with pytest.raises(ValueError, match="active meetings"):
            await delete_body(session, body.id)

    @pytest.mark.asyncio
    async def test_not_found_raises_value_error(self) -> None:
        """Non-existent body raises ValueError."""
        session = _mock_session()
        with pytest.raises(ValueError, match="not found"):
            await delete_body(session, uuid.uuid4())
