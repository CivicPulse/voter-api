"""Unit tests for meeting search schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from voter_api.schemas.meeting_search import (
    MatchSourceEnum,
    PaginatedSearchResultResponse,
    SearchResultItem,
)


class TestMatchSourceEnum:
    def test_agenda_item_value(self):
        assert MatchSourceEnum.AGENDA_ITEM == "agenda_item"

    def test_attachment_filename_value(self):
        assert MatchSourceEnum.ATTACHMENT_FILENAME == "attachment_filename"


class TestSearchResultItem:
    def _valid_data(self, **overrides):
        defaults = {
            "agenda_item_id": uuid.uuid4(),
            "title": "Budget Discussion",
            "description_excerpt": "Discussion of the annual budget...",
            "meeting_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "governing_body_id": uuid.uuid4(),
            "governing_body_name": "City Council",
            "match_source": "agenda_item",
            "relevance_score": 0.85,
        }
        defaults.update(overrides)
        return defaults

    def test_valid_result(self):
        item = SearchResultItem(**self._valid_data())
        assert item.title == "Budget Discussion"
        assert item.match_source == MatchSourceEnum.AGENDA_ITEM

    def test_description_excerpt_optional(self):
        item = SearchResultItem(**self._valid_data(description_excerpt=None))
        assert item.description_excerpt is None

    def test_relevance_score_default(self):
        data = self._valid_data()
        del data["relevance_score"]
        item = SearchResultItem(**data)
        assert item.relevance_score == pytest.approx(0.0)

    def test_attachment_match_source(self):
        item = SearchResultItem(**self._valid_data(match_source="attachment_filename"))
        assert item.match_source == MatchSourceEnum.ATTACHMENT_FILENAME

    def test_invalid_match_source_rejected(self):
        with pytest.raises(ValidationError):
            SearchResultItem(**self._valid_data(match_source="invalid"))

    def test_missing_required_field_rejected(self):
        data = self._valid_data()
        del data["title"]
        with pytest.raises(ValidationError):
            SearchResultItem(**data)


class TestPaginatedSearchResultResponse:
    def test_empty_results(self):
        resp = PaginatedSearchResultResponse(
            items=[],
            pagination={"total": 0, "page": 1, "page_size": 20, "total_pages": 0},
        )
        assert resp.items == []
        assert resp.pagination.total == 0

    def test_with_results(self):
        item_data = {
            "agenda_item_id": uuid.uuid4(),
            "title": "Test",
            "meeting_id": uuid.uuid4(),
            "meeting_date": datetime.now(UTC),
            "meeting_type": "regular",
            "governing_body_id": uuid.uuid4(),
            "governing_body_name": "Board",
            "match_source": "agenda_item",
        }
        resp = PaginatedSearchResultResponse(
            items=[item_data],
            pagination={"total": 1, "page": 1, "page_size": 20, "total_pages": 1},
        )
        assert len(resp.items) == 1
        assert resp.pagination.total == 1
