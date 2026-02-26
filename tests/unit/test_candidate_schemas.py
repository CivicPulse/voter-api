"""Unit tests for candidate Pydantic schemas."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from voter_api.schemas.candidate import (
    CandidateCreateRequest,
    CandidateDetailResponse,
    CandidateLinkCreateRequest,
    CandidateSummaryResponse,
    CandidateUpdateRequest,
    FilingStatus,
    LinkType,
)


class TestFilingStatusEnum:
    """Tests for FilingStatus enum values."""

    def test_all_values(self):
        assert FilingStatus.QUALIFIED == "qualified"
        assert FilingStatus.WITHDRAWN == "withdrawn"
        assert FilingStatus.DISQUALIFIED == "disqualified"
        assert FilingStatus.WRITE_IN == "write_in"


class TestLinkTypeEnum:
    """Tests for LinkType enum values."""

    def test_all_values(self):
        expected = {"website", "campaign", "facebook", "twitter", "instagram", "youtube", "linkedin", "other"}
        assert {lt.value for lt in LinkType} == expected


class TestCandidateCreateRequest:
    """Tests for CandidateCreateRequest schema validation."""

    def test_minimal_valid_request(self):
        req = CandidateCreateRequest(full_name="Jane Doe")
        assert req.full_name == "Jane Doe"
        assert req.party is None
        assert req.bio is None
        assert req.photo_url is None
        assert req.ballot_order is None
        assert req.filing_status == FilingStatus.QUALIFIED
        assert req.is_incumbent is False
        assert req.sos_ballot_option_id is None
        assert req.links == []

    def test_full_request(self):
        req = CandidateCreateRequest(
            full_name="Andrea Cooke",
            party="Independent",
            bio="Community advocate.",
            photo_url="https://example.com/photo.jpg",
            ballot_order=1,
            filing_status=FilingStatus.QUALIFIED,
            is_incumbent=True,
            sos_ballot_option_id="opt-123",
            links=[
                CandidateLinkCreateRequest(link_type=LinkType.CAMPAIGN, url="https://cooke2026.com"),
            ],
        )
        assert req.full_name == "Andrea Cooke"
        assert req.party == "Independent"
        assert req.is_incumbent is True
        assert len(req.links) == 1

    def test_full_name_required(self):
        with pytest.raises(ValidationError):
            CandidateCreateRequest()

    def test_full_name_min_length(self):
        with pytest.raises(ValidationError):
            CandidateCreateRequest(full_name="")

    def test_full_name_max_length(self):
        with pytest.raises(ValidationError):
            CandidateCreateRequest(full_name="x" * 201)

    def test_invalid_filing_status(self):
        with pytest.raises(ValidationError):
            CandidateCreateRequest(full_name="Test", filing_status="invalid")

    def test_filing_status_enum_values(self):
        for status in FilingStatus:
            req = CandidateCreateRequest(full_name="Test", filing_status=status)
            assert req.filing_status == status


class TestCandidateUpdateRequest:
    """Tests for CandidateUpdateRequest schema validation."""

    def test_empty_update_is_valid(self):
        req = CandidateUpdateRequest()
        assert req.model_dump(exclude_unset=True) == {}

    def test_partial_update(self):
        req = CandidateUpdateRequest(filing_status=FilingStatus.WITHDRAWN)
        data = req.model_dump(exclude_unset=True)
        assert data == {"filing_status": "withdrawn"}

    def test_full_name_cannot_be_empty_string(self):
        with pytest.raises(ValidationError):
            CandidateUpdateRequest(full_name="")

    def test_full_name_can_be_set(self):
        req = CandidateUpdateRequest(full_name="New Name")
        assert req.full_name == "New Name"


class TestCandidateLinkCreateRequest:
    """Tests for CandidateLinkCreateRequest schema validation."""

    def test_valid_link(self):
        req = CandidateLinkCreateRequest(link_type=LinkType.WEBSITE, url="https://example.com")
        assert req.link_type == LinkType.WEBSITE
        assert req.url == "https://example.com"
        assert req.label is None

    def test_link_with_label(self):
        req = CandidateLinkCreateRequest(link_type=LinkType.CAMPAIGN, url="https://vote.com", label="My Campaign")
        assert req.label == "My Campaign"

    def test_link_type_required(self):
        with pytest.raises(ValidationError):
            CandidateLinkCreateRequest(url="https://example.com")

    def test_url_required(self):
        with pytest.raises(ValidationError):
            CandidateLinkCreateRequest(link_type=LinkType.WEBSITE)

    def test_invalid_link_type(self):
        with pytest.raises(ValidationError):
            CandidateLinkCreateRequest(link_type="invalid", url="https://example.com")

    def test_all_link_types_valid(self):
        for lt in LinkType:
            req = CandidateLinkCreateRequest(link_type=lt, url="https://example.com")
            assert req.link_type == lt


class TestCandidateSummaryResponse:
    """Tests for CandidateSummaryResponse from_attributes ORM mapping."""

    def test_from_attributes(self):
        class FakeCandidate:
            id = uuid.uuid4()
            election_id = uuid.uuid4()
            full_name = "Test Candidate"
            party = None
            photo_url = None
            ballot_order = 1
            filing_status = "qualified"
            is_incumbent = False
            created_at = datetime(2026, 1, 1, tzinfo=UTC)

        resp = CandidateSummaryResponse.model_validate(FakeCandidate())
        assert resp.full_name == "Test Candidate"
        assert resp.filing_status == "qualified"
        assert resp.is_incumbent is False


class TestCandidateDetailResponse:
    """Tests for CandidateDetailResponse schema."""

    def test_includes_extended_fields(self):
        resp = CandidateDetailResponse(
            id=uuid.uuid4(),
            election_id=uuid.uuid4(),
            full_name="Test",
            filing_status="qualified",
            is_incumbent=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            links=[],
        )
        assert resp.bio is None
        assert resp.sos_ballot_option_id is None
        assert resp.result_vote_count is None
        assert resp.result_political_party is None
        assert resp.links == []

    def test_with_result_data(self):
        resp = CandidateDetailResponse(
            id=uuid.uuid4(),
            election_id=uuid.uuid4(),
            full_name="Test",
            filing_status="qualified",
            is_incumbent=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            links=[],
            result_vote_count=1234,
            result_political_party="Dem",
        )
        assert resp.result_vote_count == 1234
        assert resp.result_political_party == "Dem"
