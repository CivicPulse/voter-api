"""Contract tests validating meeting records Pydantic schemas match OpenAPI spec.

Verifies all meeting record response schemas can be instantiated with expected
fields and produce valid JSON-serializable output matching contracts/openapi.yaml.
"""

import uuid
from datetime import UTC, datetime

from voter_api.schemas.agenda_item import (
    AgendaItemCreateRequest,
    AgendaItemReorderRequest,
    AgendaItemResponse,
    AgendaItemUpdateRequest,
    DispositionEnum,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.governing_body import (
    GoverningBodyCreateRequest,
    GoverningBodyDetailResponse,
    GoverningBodySummaryResponse,
    GoverningBodyUpdateRequest,
    PaginatedGoverningBodyResponse,
)
from voter_api.schemas.governing_body_type import (
    GoverningBodyTypeCreateRequest,
    GoverningBodyTypeResponse,
)
from voter_api.schemas.meeting import (
    MeetingCreateRequest,
    MeetingDetailResponse,
    MeetingRejectRequest,
    MeetingSummaryResponse,
    MeetingUpdateRequest,
    PaginatedMeetingResponse,
)
from voter_api.schemas.meeting_attachment import AttachmentResponse
from voter_api.schemas.meeting_search import (
    MatchSourceEnum,
    PaginatedSearchResultResponse,
    SearchResultItem,
)
from voter_api.schemas.meeting_video_embed import (
    VideoEmbedCreateRequest,
    VideoEmbedResponse,
    VideoEmbedUpdateRequest,
)

# ---------------------------------------------------------------------------
# Governing Body Types
# ---------------------------------------------------------------------------


class TestGoverningBodyTypeResponse:
    def test_required_fields(self):
        resp = GoverningBodyTypeResponse(
            id=uuid.uuid4(),
            name="County Commission",
            slug="county-commission",
            is_default=True,
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert "id" in data
        assert data["name"] == "County Commission"
        assert data["slug"] == "county-commission"
        assert data["is_default"] is True

    def test_optional_description(self):
        resp = GoverningBodyTypeResponse(
            id=uuid.uuid4(),
            name="Custom Type",
            slug="custom-type",
            is_default=False,
            description="A custom body type",
            created_at=datetime.now(UTC),
        )
        assert resp.description == "A custom body type"


class TestGoverningBodyTypeCreateRequest:
    def test_valid_request(self):
        req = GoverningBodyTypeCreateRequest(name="Water Authority")
        data = req.model_dump()
        assert data["name"] == "Water Authority"

    def test_optional_description(self):
        req = GoverningBodyTypeCreateRequest(name="Transit Authority", description="Public transit")
        assert req.description == "Public transit"


# ---------------------------------------------------------------------------
# Governing Bodies
# ---------------------------------------------------------------------------


class TestGoverningBodySummaryResponse:
    def test_required_fields(self):
        body_type = GoverningBodyTypeResponse(
            id=uuid.uuid4(),
            name="County Commission",
            slug="county-commission",
            is_default=True,
            created_at=datetime.now(UTC),
        )
        resp = GoverningBodySummaryResponse(
            id=uuid.uuid4(),
            name="Fulton County Commission",
            type=body_type,
            jurisdiction="Fulton County, GA",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert "id" in data
        assert data["name"] == "Fulton County Commission"
        assert data["jurisdiction"] == "Fulton County, GA"


class TestGoverningBodyDetailResponse:
    def test_with_meeting_count(self):
        body_type = GoverningBodyTypeResponse(
            id=uuid.uuid4(),
            name="City Council",
            slug="city-council",
            is_default=True,
            created_at=datetime.now(UTC),
        )
        resp = GoverningBodyDetailResponse(
            id=uuid.uuid4(),
            name="Atlanta City Council",
            type=body_type,
            jurisdiction="City of Atlanta, GA",
            meeting_count=42,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["meeting_count"] == 42


class TestGoverningBodyCreateRequest:
    def test_required_fields(self):
        req = GoverningBodyCreateRequest(
            name="DeKalb County Commission",
            type_id=uuid.uuid4(),
            jurisdiction="DeKalb County, GA",
        )
        data = req.model_dump()
        assert data["name"] == "DeKalb County Commission"

    def test_optional_fields(self):
        req = GoverningBodyCreateRequest(
            name="Cobb Board of Education",
            type_id=uuid.uuid4(),
            jurisdiction="Cobb County, GA",
            description="Public school oversight",
            website_url="https://cobbk12.org",
        )
        assert str(req.website_url).rstrip("/") == "https://cobbk12.org"


class TestGoverningBodyUpdateRequest:
    def test_partial_update(self):
        req = GoverningBodyUpdateRequest(name="Updated Name")
        data = req.model_dump(exclude_unset=True)
        assert data == {"name": "Updated Name"}


class TestPaginatedGoverningBodyResponse:
    def test_structure(self):
        resp = PaginatedGoverningBodyResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=0),
        )
        data = resp.model_dump(mode="json")
        assert data["items"] == []
        assert data["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------


class TestMeetingSummaryResponse:
    def test_required_fields(self):
        resp = MeetingSummaryResponse(
            id=uuid.uuid4(),
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="regular",
            status="scheduled",
            approval_status="approved",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["meeting_type"] == "regular"
        assert data["status"] == "scheduled"
        assert data["approval_status"] == "approved"


class TestMeetingDetailResponse:
    def test_with_child_counts(self):
        resp = MeetingDetailResponse(
            id=uuid.uuid4(),
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="special",
            status="completed",
            approval_status="approved",
            agenda_item_count=5,
            attachment_count=3,
            video_embed_count=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["agenda_item_count"] == 5
        assert data["attachment_count"] == 3
        assert data["video_embed_count"] == 1


class TestMeetingCreateRequest:
    def test_required_fields(self):
        req = MeetingCreateRequest(
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="regular",
            status="scheduled",
        )
        data = req.model_dump()
        assert data["meeting_type"] == "regular"

    def test_optional_external_url(self):
        req = MeetingCreateRequest(
            governing_body_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="public_hearing",
            status="scheduled",
            external_source_url="https://council.example.com/meeting/123",
        )
        assert req.external_source_url == "https://council.example.com/meeting/123"


class TestMeetingUpdateRequest:
    def test_partial_update(self):
        req = MeetingUpdateRequest(status="completed")
        data = req.model_dump(exclude_unset=True)
        assert data == {"status": "completed"}


class TestMeetingRejectRequest:
    def test_with_reason(self):
        req = MeetingRejectRequest(reason="Duplicate entry")
        assert req.reason == "Duplicate entry"


class TestPaginatedMeetingResponse:
    def test_structure(self):
        resp = PaginatedMeetingResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=0),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data


# ---------------------------------------------------------------------------
# Agenda Items
# ---------------------------------------------------------------------------


class TestAgendaItemResponse:
    def test_required_fields(self):
        resp = AgendaItemResponse(
            id=uuid.uuid4(),
            meeting_id=uuid.uuid4(),
            title="Approval of Minutes",
            display_order=10,
            attachment_count=0,
            video_embed_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["title"] == "Approval of Minutes"
        assert data["display_order"] == 10

    def test_optional_disposition(self):
        resp = AgendaItemResponse(
            id=uuid.uuid4(),
            meeting_id=uuid.uuid4(),
            title="Budget Vote",
            display_order=20,
            disposition="approved",
            attachment_count=2,
            video_embed_count=1,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert resp.disposition == DispositionEnum.APPROVED


class TestAgendaItemCreateRequest:
    def test_required_fields(self):
        req = AgendaItemCreateRequest(title="New Business")
        data = req.model_dump()
        assert data["title"] == "New Business"

    def test_optional_display_order(self):
        req = AgendaItemCreateRequest(title="Item", display_order=5)
        assert req.display_order == 5


class TestAgendaItemUpdateRequest:
    def test_partial_update(self):
        req = AgendaItemUpdateRequest(disposition="tabled")
        data = req.model_dump(exclude_unset=True)
        assert data == {"disposition": "tabled"}


class TestAgendaItemReorderRequest:
    def test_valid_request(self):
        ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
        req = AgendaItemReorderRequest(item_ids=ids)
        assert len(req.item_ids) == 3


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------


class TestAttachmentResponse:
    def test_required_fields(self):
        resp = AttachmentResponse(
            id=uuid.uuid4(),
            original_filename="budget.pdf",
            file_size=1024,
            content_type="application/pdf",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["original_filename"] == "budget.pdf"
        assert data["file_size"] == 1024
        assert data["content_type"] == "application/pdf"

    def test_optional_parent_ids(self):
        mid = uuid.uuid4()
        resp = AttachmentResponse(
            id=uuid.uuid4(),
            meeting_id=mid,
            original_filename="minutes.docx",
            file_size=2048,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            download_url="/api/v1/attachments/abc/download",
            created_at=datetime.now(UTC),
        )
        assert resp.meeting_id == mid
        assert resp.download_url is not None


# ---------------------------------------------------------------------------
# Video Embeds
# ---------------------------------------------------------------------------


class TestVideoEmbedResponse:
    def test_required_fields(self):
        resp = VideoEmbedResponse(
            id=uuid.uuid4(),
            video_url="https://www.youtube.com/watch?v=test",
            platform="youtube",
            created_at=datetime.now(UTC),
        )
        data = resp.model_dump(mode="json")
        assert data["platform"] == "youtube"

    def test_with_timestamps(self):
        resp = VideoEmbedResponse(
            id=uuid.uuid4(),
            video_url="https://vimeo.com/123456",
            platform="vimeo",
            start_seconds=120,
            end_seconds=3600,
            created_at=datetime.now(UTC),
        )
        assert resp.start_seconds == 120
        assert resp.end_seconds == 3600


class TestVideoEmbedCreateRequest:
    def test_required_fields(self):
        req = VideoEmbedCreateRequest(video_url="https://www.youtube.com/watch?v=test")
        data = req.model_dump()
        assert data["video_url"] == "https://www.youtube.com/watch?v=test"

    def test_optional_timestamps(self):
        req = VideoEmbedCreateRequest(
            video_url="https://vimeo.com/123",
            start_seconds=60,
            end_seconds=300,
        )
        assert req.start_seconds == 60


class TestVideoEmbedUpdateRequest:
    def test_partial_update(self):
        req = VideoEmbedUpdateRequest(start_seconds=30)
        data = req.model_dump(exclude_unset=True)
        assert data == {"start_seconds": 30}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearchResultItem:
    def test_required_fields(self):
        item = SearchResultItem(
            agenda_item_id=uuid.uuid4(),
            title="Budget Discussion",
            meeting_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="regular",
            governing_body_id=uuid.uuid4(),
            governing_body_name="City Council",
            match_source="agenda_item",
        )
        data = item.model_dump(mode="json")
        assert data["title"] == "Budget Discussion"
        assert data["match_source"] == "agenda_item"

    def test_attachment_match(self):
        item = SearchResultItem(
            agenda_item_id=uuid.uuid4(),
            title="minutes.pdf",
            meeting_id=uuid.uuid4(),
            meeting_date=datetime.now(UTC),
            meeting_type="regular",
            governing_body_id=uuid.uuid4(),
            governing_body_name="Board",
            match_source="attachment_filename",
            relevance_score=0.1,
        )
        assert item.match_source == MatchSourceEnum.ATTACHMENT_FILENAME


class TestPaginatedSearchResultResponse:
    def test_structure(self):
        resp = PaginatedSearchResultResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=0),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data
        assert data["pagination"]["total"] == 0
