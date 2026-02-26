"""Contract tests validating candidate Pydantic schemas match OpenAPI spec.

Verifies all candidate response schemas can be instantiated with expected fields
and produce valid JSON-serializable output matching
specs/010-election-info/contracts/openapi.yaml.
"""

import uuid
from datetime import UTC, datetime

import pytest

from voter_api.schemas.candidate import (
    CandidateDetailResponse,
    CandidateLinkResponse,
    CandidateSummaryResponse,
    FilingStatus,
    LinkType,
    PaginatedCandidateResponse,
)
from voter_api.schemas.common import PaginationMeta

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 25, 12, 0, 0, tzinfo=UTC)
ELECTION_ID = uuid.uuid4()
CANDIDATE_ID = uuid.uuid4()
LINK_ID = uuid.uuid4()


def _make_summary(**overrides) -> CandidateSummaryResponse:
    """Build a valid CandidateSummaryResponse with sensible defaults."""
    defaults = {
        "id": CANDIDATE_ID,
        "election_id": ELECTION_ID,
        "full_name": "Andrea C. Cooke",
        "filing_status": "qualified",
        "is_incumbent": False,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return CandidateSummaryResponse(**defaults)


def _make_link(**overrides) -> CandidateLinkResponse:
    """Build a valid CandidateLinkResponse with sensible defaults."""
    defaults = {
        "id": LINK_ID,
        "link_type": "campaign",
        "url": "https://www.candidate2026.com",
    }
    defaults.update(overrides)
    return CandidateLinkResponse(**defaults)


def _make_detail(**overrides) -> CandidateDetailResponse:
    """Build a valid CandidateDetailResponse with sensible defaults."""
    defaults = {
        "id": CANDIDATE_ID,
        "election_id": ELECTION_ID,
        "full_name": "Andrea C. Cooke",
        "filing_status": "qualified",
        "is_incumbent": False,
        "created_at": NOW,
        "updated_at": NOW,
        "links": [],
    }
    defaults.update(overrides)
    return CandidateDetailResponse(**defaults)


# ---------------------------------------------------------------------------
# PaginatedCandidateResponse shape
# ---------------------------------------------------------------------------


class TestPaginatedCandidateResponseShape:
    """Verify paginated candidate list matches OpenAPI PaginatedCandidateResponse."""

    def test_has_items_and_pagination(self):
        resp = PaginatedCandidateResponse(
            items=[_make_summary()],
            pagination=PaginationMeta(total=1, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data

    def test_items_is_array(self):
        resp = PaginatedCandidateResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=0),
        )
        data = resp.model_dump(mode="json")
        assert isinstance(data["items"], list)

    def test_pagination_required_fields(self):
        resp = PaginatedCandidateResponse(
            items=[],
            pagination=PaginationMeta(total=42, page=3, page_size=10, total_pages=5),
        )
        pag = resp.model_dump(mode="json")["pagination"]
        assert pag["total"] == 42
        assert pag["page"] == 3
        assert pag["page_size"] == 10
        assert pag["total_pages"] == 5

    def test_items_contain_summary_objects(self):
        resp = PaginatedCandidateResponse(
            items=[_make_summary(), _make_summary(id=uuid.uuid4(), full_name="Bob Jones")],
            pagination=PaginationMeta(total=2, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert len(data["items"]) == 2
        assert data["items"][0]["full_name"] == "Andrea C. Cooke"
        assert data["items"][1]["full_name"] == "Bob Jones"


# ---------------------------------------------------------------------------
# CandidateSummaryResponse required fields
# ---------------------------------------------------------------------------


class TestCandidateSummaryResponseFields:
    """Verify CandidateSummaryResponse required fields per OpenAPI spec."""

    def test_required_fields_present(self):
        summary = _make_summary()
        data = summary.model_dump(mode="json")
        for field in ("id", "election_id", "full_name", "filing_status", "is_incumbent", "created_at"):
            assert field in data, f"Required field '{field}' missing from CandidateSummaryResponse"

    def test_optional_fields_nullable(self):
        summary = _make_summary()
        data = summary.model_dump(mode="json")
        assert data["party"] is None
        assert data["photo_url"] is None
        assert data["ballot_order"] is None

    def test_optional_fields_populated(self):
        summary = _make_summary(
            party="Democratic",
            photo_url="https://example.com/photo.jpg",
            ballot_order=2,
        )
        data = summary.model_dump(mode="json")
        assert data["party"] == "Democratic"
        assert data["photo_url"] == "https://example.com/photo.jpg"
        assert data["ballot_order"] == 2

    def test_id_serializes_as_string(self):
        summary = _make_summary()
        data = summary.model_dump(mode="json")
        assert isinstance(data["id"], str)
        assert isinstance(data["election_id"], str)

    def test_created_at_serializes_as_string(self):
        summary = _make_summary()
        data = summary.model_dump(mode="json")
        assert isinstance(data["created_at"], str)


# ---------------------------------------------------------------------------
# CandidateDetailResponse required fields
# ---------------------------------------------------------------------------


class TestCandidateDetailResponseFields:
    """Verify CandidateDetailResponse has all summary fields plus detail-only fields."""

    def test_has_all_summary_fields(self):
        detail = _make_detail()
        data = detail.model_dump(mode="json")
        for field in ("id", "election_id", "full_name", "filing_status", "is_incumbent", "created_at"):
            assert field in data, f"Summary field '{field}' missing from CandidateDetailResponse"

    def test_has_updated_at(self):
        detail = _make_detail()
        data = detail.model_dump(mode="json")
        assert "updated_at" in data
        assert isinstance(data["updated_at"], str)

    def test_has_links_array(self):
        detail = _make_detail()
        data = detail.model_dump(mode="json")
        assert "links" in data
        assert isinstance(data["links"], list)

    def test_links_populated(self):
        link = _make_link()
        detail = _make_detail(links=[link])
        data = detail.model_dump(mode="json")
        assert len(data["links"]) == 1
        assert data["links"][0]["link_type"] == "campaign"
        assert data["links"][0]["url"] == "https://www.candidate2026.com"

    def test_optional_detail_fields_nullable(self):
        detail = _make_detail()
        data = detail.model_dump(mode="json")
        assert data["bio"] is None
        assert data["sos_ballot_option_id"] is None
        assert data["result_vote_count"] is None
        assert data["result_political_party"] is None

    def test_optional_detail_fields_populated(self):
        detail = _make_detail(
            bio="Community advocate.",
            sos_ballot_option_id="opt-12345",
            result_vote_count=1234,
            result_political_party="Republican",
        )
        data = detail.model_dump(mode="json")
        assert data["bio"] == "Community advocate."
        assert data["sos_ballot_option_id"] == "opt-12345"
        assert data["result_vote_count"] == 1234
        assert data["result_political_party"] == "Republican"


# ---------------------------------------------------------------------------
# CandidateLinkResponse required fields
# ---------------------------------------------------------------------------


class TestCandidateLinkResponseFields:
    """Verify CandidateLinkResponse required fields per OpenAPI spec."""

    def test_required_fields_present(self):
        link = _make_link()
        data = link.model_dump(mode="json")
        for field in ("id", "link_type", "url"):
            assert field in data, f"Required field '{field}' missing from CandidateLinkResponse"

    def test_label_optional_defaults_to_none(self):
        link = _make_link()
        data = link.model_dump(mode="json")
        assert data["label"] is None

    def test_label_populated(self):
        link = _make_link(label="Campaign Website")
        data = link.model_dump(mode="json")
        assert data["label"] == "Campaign Website"

    def test_id_serializes_as_string(self):
        link = _make_link()
        data = link.model_dump(mode="json")
        assert isinstance(data["id"], str)


# ---------------------------------------------------------------------------
# FilingStatus enum values
# ---------------------------------------------------------------------------


class TestFilingStatusEnum:
    """Verify FilingStatus enum matches the OpenAPI filing_status values."""

    EXPECTED_VALUES = {"qualified", "withdrawn", "disqualified", "write_in"}

    def test_all_expected_values_exist(self):
        actual = {member.value for member in FilingStatus}
        assert actual == self.EXPECTED_VALUES

    @pytest.mark.parametrize("value", ["qualified", "withdrawn", "disqualified", "write_in"])
    def test_each_value_valid(self, value: str):
        status = FilingStatus(value)
        assert status.value == value

    def test_no_extra_values(self):
        actual = {member.value for member in FilingStatus}
        assert len(actual) == 4

    def test_enum_is_str_compatible(self):
        """FilingStatus should be usable as a string (StrEnum)."""
        assert FilingStatus.QUALIFIED == "qualified"
        assert str(FilingStatus.WITHDRAWN) == "withdrawn"


# ---------------------------------------------------------------------------
# LinkType enum values
# ---------------------------------------------------------------------------


class TestLinkTypeEnum:
    """Verify LinkType enum matches the OpenAPI link_type values."""

    EXPECTED_VALUES = {"website", "campaign", "facebook", "twitter", "instagram", "youtube", "linkedin", "other"}

    def test_all_expected_values_exist(self):
        actual = {member.value for member in LinkType}
        assert actual == self.EXPECTED_VALUES

    @pytest.mark.parametrize(
        "value",
        ["website", "campaign", "facebook", "twitter", "instagram", "youtube", "linkedin", "other"],
    )
    def test_each_value_valid(self, value: str):
        lt = LinkType(value)
        assert lt.value == value

    def test_no_extra_values(self):
        actual = {member.value for member in LinkType}
        assert len(actual) == 8

    def test_enum_is_str_compatible(self):
        """LinkType should be usable as a string (StrEnum)."""
        assert LinkType.WEBSITE == "website"
        assert str(LinkType.OTHER) == "other"
