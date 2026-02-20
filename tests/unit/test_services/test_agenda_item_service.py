"""Unit tests for agenda item service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.agenda_item_service import (
    create_item,
    delete_item,
    get_item,
    get_item_child_counts,
    list_items,
    reorder_items,
    update_item,
)


def _mock_session() -> AsyncMock:
    return AsyncMock()


def _mock_item(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "title": "Budget Approval",
        "description": "Review Q2 budget",
        "action_taken": None,
        "disposition": None,
        "display_order": 10,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestListItems:
    @pytest.mark.asyncio
    async def test_returns_items(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()
        items = [
            _mock_item(meeting_id=meeting_id, display_order=10),
            _mock_item(meeting_id=meeting_id, display_order=20),
        ]

        # _require_meeting returns a meeting ID
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        # list query returns items
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = items

        session.execute = AsyncMock(side_effect=[meeting_result, list_result])

        result = await list_items(session, meeting_id)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_meeting_not_found_raises(self) -> None:
        session = _mock_session()
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=meeting_result)

        with pytest.raises(ValueError, match="Meeting .* not found"):
            await list_items(session, uuid.uuid4())


class TestGetItem:
    @pytest.mark.asyncio
    async def test_returns_item(self) -> None:
        session = _mock_session()
        item = _mock_item()
        result = MagicMock()
        result.scalar_one_or_none.return_value = item
        session.execute = AsyncMock(return_value=result)

        found = await get_item(session, item.meeting_id, item.id)
        assert found is item

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self) -> None:
        session = _mock_session()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        found = await get_item(session, uuid.uuid4(), uuid.uuid4())
        assert found is None


class TestGetItemChildCounts:
    @pytest.mark.asyncio
    async def test_returns_counts(self) -> None:
        session = _mock_session()
        att_result = MagicMock()
        att_result.scalar_one.return_value = 3
        vid_result = MagicMock()
        vid_result.scalar_one.return_value = 1
        session.execute = AsyncMock(side_effect=[att_result, vid_result])

        att_count, vid_count = await get_item_child_counts(session, uuid.uuid4())
        assert att_count == 3
        assert vid_count == 1


class TestCreateItem:
    @pytest.mark.asyncio
    async def test_auto_append_order(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()

        # _require_meeting
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        # max order query
        max_result = MagicMock()
        max_result.scalar_one.return_value = 20

        session.execute = AsyncMock(side_effect=[meeting_result, max_result])

        await create_item(session, meeting_id=meeting_id, data={"title": "New Item"})
        # Item should be a real AgendaItem created with display_order = 20 + 10 = 30
        session.add.assert_called_once()
        created = session.add.call_args[0][0]
        assert created.display_order == 30
        assert created.title == "New Item"

    @pytest.mark.asyncio
    async def test_auto_append_empty_meeting(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        max_result = MagicMock()
        max_result.scalar_one.return_value = None  # No items yet

        session.execute = AsyncMock(side_effect=[meeting_result, max_result])

        await create_item(session, meeting_id=meeting_id, data={"title": "First Item"})
        created = session.add.call_args[0][0]
        assert created.display_order == 10  # (0 + 10)

    @pytest.mark.asyncio
    async def test_explicit_order(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        session.execute = AsyncMock(return_value=meeting_result)

        await create_item(session, meeting_id=meeting_id, data={"title": "Item", "display_order": 5})
        created = session.add.call_args[0][0]
        assert created.display_order == 5

    @pytest.mark.asyncio
    async def test_meeting_not_found_raises(self) -> None:
        session = _mock_session()
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=meeting_result)

        with pytest.raises(ValueError, match="Meeting .* not found"):
            await create_item(session, meeting_id=uuid.uuid4(), data={"title": "Item"})


class TestUpdateItem:
    @pytest.mark.asyncio
    async def test_updates_fields(self) -> None:
        session = _mock_session()
        item = _mock_item()

        with patch(
            "voter_api.services.agenda_item_service.get_item",
            new_callable=AsyncMock,
            return_value=item,
        ):
            result = await update_item(
                session, item.meeting_id, item.id, data={"title": "Updated", "disposition": "tabled"}
            )

        assert result.title == "Updated"
        assert result.disposition == "tabled"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = _mock_session()

        with (
            patch(
                "voter_api.services.agenda_item_service.get_item",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await update_item(session, uuid.uuid4(), uuid.uuid4(), data={"title": "X"})

    @pytest.mark.asyncio
    async def test_ignores_non_updatable_fields(self) -> None:
        session = _mock_session()
        item = _mock_item()
        original_order = item.display_order

        with patch(
            "voter_api.services.agenda_item_service.get_item",
            new_callable=AsyncMock,
            return_value=item,
        ):
            await update_item(session, item.meeting_id, item.id, data={"display_order": 999})

        assert item.display_order == original_order


class TestDeleteItem:
    @pytest.mark.asyncio
    async def test_soft_deletes_with_cascade(self) -> None:
        session = _mock_session()
        item = _mock_item()

        att = MagicMock()
        att.deleted_at = None
        vid = MagicMock()
        vid.deleted_at = None

        att_result = MagicMock()
        att_result.scalars.return_value.all.return_value = [att]
        vid_result = MagicMock()
        vid_result.scalars.return_value.all.return_value = [vid]

        session.execute = AsyncMock(side_effect=[att_result, vid_result])

        with patch(
            "voter_api.services.agenda_item_service.get_item",
            new_callable=AsyncMock,
            return_value=item,
        ):
            await delete_item(session, item.meeting_id, item.id)

        assert item.deleted_at is not None
        assert att.deleted_at is not None
        assert vid.deleted_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = _mock_session()

        with (
            patch(
                "voter_api.services.agenda_item_service.get_item",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await delete_item(session, uuid.uuid4(), uuid.uuid4())


class TestReorderItems:
    @pytest.mark.asyncio
    async def test_reorders_successfully(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()
        item_a = _mock_item(meeting_id=meeting_id, display_order=10)
        item_b = _mock_item(meeting_id=meeting_id, display_order=20)

        # _require_meeting
        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        # Fetch existing items
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item_a, item_b]

        session.execute = AsyncMock(side_effect=[meeting_result, items_result])

        # Reorder: B first, then A
        with patch(
            "voter_api.services.agenda_item_service.list_items",
            new_callable=AsyncMock,
            return_value=[item_b, item_a],
        ):
            result = await reorder_items(session, meeting_id, [item_b.id, item_a.id])

        assert item_b.display_order == 10  # (0+1)*10
        assert item_a.display_order == 20  # (1+1)*10
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_invalid_item_raises(self) -> None:
        session = _mock_session()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[meeting_result, items_result])

        with pytest.raises(ValueError, match="not found in meeting"):
            await reorder_items(session, meeting_id, [uuid.uuid4()])
