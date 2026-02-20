"""Unit tests for agenda item schemas."""

import uuid

import pytest
from pydantic import ValidationError

from voter_api.schemas.agenda_item import (
    AgendaItemCreateRequest,
    AgendaItemReorderRequest,
    AgendaItemResponse,
    AgendaItemUpdateRequest,
    DispositionEnum,
)


class TestDispositionEnum:
    def test_values(self) -> None:
        assert DispositionEnum.APPROVED == "approved"
        assert DispositionEnum.DENIED == "denied"
        assert DispositionEnum.TABLED == "tabled"
        assert DispositionEnum.NO_ACTION == "no_action"
        assert DispositionEnum.INFORMATIONAL == "informational"

    def test_all_values_count(self) -> None:
        assert len(DispositionEnum) == 5


class TestAgendaItemResponse:
    def test_valid_response(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "meeting_id": uuid.uuid4(),
            "title": "Budget Approval",
            "description": "Review and approve Q2 budget",
            "action_taken": "Voted unanimously to approve",
            "disposition": "approved",
            "display_order": 10,
            "attachment_count": 2,
            "video_embed_count": 1,
            "created_at": "2026-03-15T18:00:00Z",
            "updated_at": "2026-03-15T18:00:00Z",
        }
        resp = AgendaItemResponse(**data)
        assert resp.title == "Budget Approval"
        assert resp.disposition == DispositionEnum.APPROVED
        assert resp.attachment_count == 2

    def test_nullable_fields_default_none(self) -> None:
        data = {
            "id": uuid.uuid4(),
            "meeting_id": uuid.uuid4(),
            "title": "Roll Call",
            "display_order": 10,
            "created_at": "2026-03-15T18:00:00Z",
            "updated_at": "2026-03-15T18:00:00Z",
        }
        resp = AgendaItemResponse(**data)
        assert resp.description is None
        assert resp.action_taken is None
        assert resp.disposition is None
        assert resp.attachment_count == 0
        assert resp.video_embed_count == 0


class TestAgendaItemCreateRequest:
    def test_minimal_valid(self) -> None:
        req = AgendaItemCreateRequest(title="Roll Call")
        assert req.title == "Roll Call"
        assert req.display_order is None
        assert req.disposition is None

    def test_with_all_fields(self) -> None:
        req = AgendaItemCreateRequest(
            title="Budget Approval",
            description="Review Q2 budget",
            action_taken="Approved",
            disposition="approved",
            display_order=20,
        )
        assert req.display_order == 20
        assert req.disposition == DispositionEnum.APPROVED

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgendaItemCreateRequest(title="")

    def test_title_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgendaItemCreateRequest(title="x" * 501)

    def test_negative_display_order_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgendaItemCreateRequest(title="Item", display_order=-1)

    def test_invalid_disposition_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgendaItemCreateRequest(title="Item", disposition="invalid")


class TestAgendaItemUpdateRequest:
    def test_all_optional(self) -> None:
        req = AgendaItemUpdateRequest()
        assert req.title is None
        assert req.description is None
        assert req.disposition is None

    def test_partial_update(self) -> None:
        req = AgendaItemUpdateRequest(disposition="tabled")
        assert req.disposition == DispositionEnum.TABLED
        assert req.title is None

    def test_exclude_unset(self) -> None:
        req = AgendaItemUpdateRequest(title="New Title")
        data = req.model_dump(exclude_unset=True)
        assert "title" in data
        assert "description" not in data


class TestAgendaItemReorderRequest:
    def test_valid_reorder(self) -> None:
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        req = AgendaItemReorderRequest(item_ids=ids)
        assert len(req.item_ids) == 3

    def test_empty_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgendaItemReorderRequest(item_ids=[])

    def test_single_item(self) -> None:
        req = AgendaItemReorderRequest(item_ids=[uuid.uuid4()])
        assert len(req.item_ids) == 1
