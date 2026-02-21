"""Unit tests for video embed schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from voter_api.schemas.meeting_video_embed import (
    VideoEmbedCreateRequest,
    VideoEmbedResponse,
    VideoEmbedUpdateRequest,
    VideoPlatformEnum,
)


class TestVideoPlatformEnum:
    def test_values(self) -> None:
        assert VideoPlatformEnum.YOUTUBE == "youtube"
        assert VideoPlatformEnum.VIMEO == "vimeo"

    def test_count(self) -> None:
        assert len(VideoPlatformEnum) == 2


class TestVideoEmbedResponse:
    def test_valid_response(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "meeting_id": uuid.uuid4(),
            "agenda_item_id": None,
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "platform": "youtube",
            "start_seconds": 120,
            "end_seconds": 300,
            "created_at": datetime.now(UTC),
        }
        resp = VideoEmbedResponse(**data)
        assert resp.platform == VideoPlatformEnum.YOUTUBE
        assert resp.start_seconds == 120

    def test_nullable_fields(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "video_url": "https://vimeo.com/123456",
            "platform": "vimeo",
            "created_at": datetime.now(UTC),
        }
        resp = VideoEmbedResponse(**data)
        assert resp.meeting_id is None
        assert resp.start_seconds is None
        assert resp.end_seconds is None


class TestVideoEmbedCreateRequest:
    def test_minimal_valid(self) -> None:
        req = VideoEmbedCreateRequest(video_url="https://www.youtube.com/watch?v=test")
        assert req.video_url == "https://www.youtube.com/watch?v=test"
        assert req.start_seconds is None
        assert req.end_seconds is None

    def test_with_timestamps(self) -> None:
        req = VideoEmbedCreateRequest(
            video_url="https://vimeo.com/123",
            start_seconds=60,
            end_seconds=180,
        )
        assert req.start_seconds == 60
        assert req.end_seconds == 180

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VideoEmbedCreateRequest(video_url="")

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VideoEmbedCreateRequest(
                video_url="https://youtube.com/watch?v=x",
                start_seconds=-1,
            )

    def test_negative_end_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VideoEmbedCreateRequest(
                video_url="https://youtube.com/watch?v=x",
                end_seconds=-5,
            )


class TestVideoEmbedUpdateRequest:
    def test_all_optional(self) -> None:
        req = VideoEmbedUpdateRequest()
        assert req.video_url is None
        assert req.start_seconds is None

    def test_partial_update(self) -> None:
        req = VideoEmbedUpdateRequest(start_seconds=30)
        data = req.model_dump(exclude_unset=True)
        assert "start_seconds" in data
        assert "video_url" not in data
