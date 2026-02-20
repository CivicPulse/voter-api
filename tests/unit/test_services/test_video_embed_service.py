"""Unit tests for video embed service."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.meeting_video_embed_service import (
    create_embed,
    delete_embed,
    get_embed,
    list_embeds,
    update_embed,
)


def _mock_embed(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "meeting_id": uuid.uuid4(),
        "agenda_item_id": None,
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "platform": "youtube",
        "start_seconds": None,
        "end_seconds": None,
        "deleted_at": None,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestListEmbeds:
    @pytest.mark.asyncio
    async def test_lists_by_meeting(self) -> None:
        session = AsyncMock()
        embeds = [_mock_embed()]
        result = MagicMock()
        result.scalars.return_value.all.return_value = embeds
        session.execute = AsyncMock(return_value=result)

        items = await list_embeds(session, meeting_id=uuid.uuid4())
        assert len(items) == 1


class TestGetEmbed:
    @pytest.mark.asyncio
    async def test_found(self) -> None:
        session = AsyncMock()
        embed = _mock_embed()
        result = MagicMock()
        result.scalar_one_or_none.return_value = embed
        session.execute = AsyncMock(return_value=result)

        found = await get_embed(session, embed.id)
        assert found is embed

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        found = await get_embed(session, uuid.uuid4())
        assert found is None


class TestCreateEmbed:
    @pytest.mark.asyncio
    async def test_youtube_url_accepted(self) -> None:
        session = AsyncMock()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id
        session.execute = AsyncMock(return_value=meeting_result)

        await create_embed(
            session,
            data={"video_url": "https://www.youtube.com/watch?v=abc"},
            meeting_id=meeting_id,
        )
        session.add.assert_called_once()
        created = session.add.call_args[0][0]
        assert created.platform == "youtube"

    @pytest.mark.asyncio
    async def test_vimeo_url_accepted(self) -> None:
        session = AsyncMock()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id
        session.execute = AsyncMock(return_value=meeting_result)

        await create_embed(
            session,
            data={"video_url": "https://vimeo.com/123456"},
            meeting_id=meeting_id,
        )
        created = session.add.call_args[0][0]
        assert created.platform == "vimeo"

    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self) -> None:
        session = AsyncMock()

        with pytest.raises(ValueError, match="Invalid video URL"):
            await create_embed(
                session,
                data={"video_url": "https://example.com/video"},
                meeting_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_with_timestamps(self) -> None:
        session = AsyncMock()
        meeting_id = uuid.uuid4()

        meeting_result = MagicMock()
        meeting_result.scalar_one_or_none.return_value = meeting_id
        session.execute = AsyncMock(return_value=meeting_result)

        await create_embed(
            session,
            data={
                "video_url": "https://youtu.be/abc",
                "start_seconds": 60,
                "end_seconds": 120,
            },
            meeting_id=meeting_id,
        )
        created = session.add.call_args[0][0]
        assert created.start_seconds == 60
        assert created.end_seconds == 120

    @pytest.mark.asyncio
    async def test_both_parents_raises(self) -> None:
        session = AsyncMock()

        with pytest.raises(ValueError, match="Exactly one of meeting_id or agenda_item_id"):
            await create_embed(
                session,
                data={"video_url": "https://www.youtube.com/watch?v=abc"},
                meeting_id=uuid.uuid4(),
                agenda_item_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_no_parent_raises(self) -> None:
        session = AsyncMock()

        with pytest.raises(ValueError, match="Exactly one of meeting_id or agenda_item_id"):
            await create_embed(
                session,
                data={"video_url": "https://www.youtube.com/watch?v=abc"},
            )

    @pytest.mark.asyncio
    async def test_invalid_timestamps_rejected(self) -> None:
        session = AsyncMock()

        with pytest.raises(ValueError, match="Invalid timestamps"):
            await create_embed(
                session,
                data={
                    "video_url": "https://youtube.com/watch?v=x",
                    "start_seconds": 100,
                    "end_seconds": 50,
                },
                meeting_id=uuid.uuid4(),
            )


class TestUpdateEmbed:
    @pytest.mark.asyncio
    async def test_updates_url_and_detects_platform(self) -> None:
        session = AsyncMock()
        embed = _mock_embed()

        with patch(
            "voter_api.services.meeting_video_embed_service.get_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            result = await update_embed(
                session,
                embed.id,
                data={"video_url": "https://vimeo.com/999"},
            )

        assert result.video_url == "https://vimeo.com/999"
        assert result.platform == "vimeo"

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.meeting_video_embed_service.get_embed",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await update_embed(session, uuid.uuid4(), data={"start_seconds": 10})

    @pytest.mark.asyncio
    async def test_invalid_url_on_update_raises(self) -> None:
        session = AsyncMock()
        embed = _mock_embed()

        with (
            patch(
                "voter_api.services.meeting_video_embed_service.get_embed",
                new_callable=AsyncMock,
                return_value=embed,
            ),
            pytest.raises(ValueError, match="Invalid video URL"),
        ):
            await update_embed(
                session,
                embed.id,
                data={"video_url": "https://example.com/nope"},
            )


class TestDeleteEmbed:
    @pytest.mark.asyncio
    async def test_soft_deletes(self) -> None:
        session = AsyncMock()
        embed = _mock_embed()

        with patch(
            "voter_api.services.meeting_video_embed_service.get_embed",
            new_callable=AsyncMock,
            return_value=embed,
        ):
            await delete_embed(session, embed.id)

        assert embed.deleted_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.meeting_video_embed_service.get_embed",
                new_callable=AsyncMock,
                return_value=None,
            ),
            pytest.raises(ValueError, match="not found"),
        ):
            await delete_embed(session, uuid.uuid4())
