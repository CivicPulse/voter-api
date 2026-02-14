"""Unit tests for elected official Pydantic schemas."""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from voter_api.schemas.elected_official import (
    ApproveOfficialRequest,
    ElectedOfficialCreateRequest,
    ElectedOfficialDetailResponse,
    ElectedOfficialSourceResponse,
    ElectedOfficialSummaryResponse,
    ElectedOfficialUpdateRequest,
    PaginatedElectedOfficialResponse,
)


class TestElectedOfficialCreateRequest:
    """Tests for ElectedOfficialCreateRequest validation."""

    def test_valid_minimal(self) -> None:
        """Minimal valid create request."""
        req = ElectedOfficialCreateRequest(
            boundary_type="congressional",
            district_identifier="5",
            full_name="Nikema Williams",
        )
        assert req.boundary_type == "congressional"
        assert req.district_identifier == "5"
        assert req.full_name == "Nikema Williams"
        assert req.party is None
        assert req.website is None

    def test_valid_full(self) -> None:
        """Fully populated create request."""
        req = ElectedOfficialCreateRequest(
            boundary_type="state_senate",
            district_identifier="39",
            full_name="Sally Harrell",
            first_name="Sally",
            last_name="Harrell",
            party="Democratic",
            title="State Senator",
            term_start_date=date(2023, 1, 9),
            term_end_date=date(2025, 1, 13),
            website="https://example.com",
            email="senator@example.com",
            phone="404-555-0100",
            office_address="18 Capitol Square, Atlanta, GA",
            external_ids={"open_states_id": "ocd-person/abc-123"},
        )
        assert req.party == "Democratic"
        assert req.external_ids == {"open_states_id": "ocd-person/abc-123"}

    def test_missing_boundary_type_rejected(self) -> None:
        """Missing required boundary_type is rejected."""
        with pytest.raises(ValidationError):
            ElectedOfficialCreateRequest(
                district_identifier="5",
                full_name="Nikema Williams",
            )

    def test_missing_full_name_rejected(self) -> None:
        """Missing required full_name is rejected."""
        with pytest.raises(ValidationError):
            ElectedOfficialCreateRequest(
                boundary_type="congressional",
                district_identifier="5",
            )


class TestElectedOfficialUpdateRequest:
    """Tests for ElectedOfficialUpdateRequest validation."""

    def test_all_fields_optional(self) -> None:
        """All fields can be omitted."""
        req = ElectedOfficialUpdateRequest()
        assert req.full_name is None
        assert req.party is None

    def test_partial_update(self) -> None:
        """Partial update with only some fields."""
        req = ElectedOfficialUpdateRequest(party="Republican", website="https://new.example.com")
        assert req.party == "Republican"
        assert req.website == "https://new.example.com"
        assert req.full_name is None

    def test_exclude_unset(self) -> None:
        """model_dump(exclude_unset=True) only includes set fields."""
        req = ElectedOfficialUpdateRequest(party="Democratic")
        dumped = req.model_dump(exclude_unset=True)
        assert dumped == {"party": "Democratic"}


class TestElectedOfficialSummaryResponse:
    """Tests for ElectedOfficialSummaryResponse."""

    def test_from_attributes(self) -> None:
        """Schema hydrates from ORM-like object."""
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.boundary_type = "congressional"
        obj.district_identifier = "5"
        obj.full_name = "Nikema Williams"
        obj.party = "Democratic"
        obj.title = "U.S. Representative"
        obj.photo_url = None
        obj.status = "approved"
        obj.created_at = datetime.now(UTC)

        resp = ElectedOfficialSummaryResponse.model_validate(obj)
        assert resp.full_name == "Nikema Williams"
        assert resp.boundary_type == "congressional"
        assert resp.status == "approved"


class TestElectedOfficialDetailResponse:
    """Tests for ElectedOfficialDetailResponse."""

    def test_includes_sources(self) -> None:
        """Detail response includes sources list."""
        source_mock = MagicMock()
        source_mock.id = uuid.uuid4()
        source_mock.source_name = "open_states"
        source_mock.source_record_id = "ocd-person/abc-123"
        source_mock.boundary_type = "congressional"
        source_mock.district_identifier = "5"
        source_mock.full_name = "Nikema Williams"
        source_mock.first_name = "Nikema"
        source_mock.last_name = "Williams"
        source_mock.party = "Democratic"
        source_mock.title = "U.S. Representative"
        source_mock.photo_url = None
        source_mock.term_start_date = None
        source_mock.term_end_date = None
        source_mock.website = None
        source_mock.email = None
        source_mock.phone = None
        source_mock.office_address = None
        source_mock.fetched_at = datetime.now(UTC)
        source_mock.is_current = True
        source_mock.created_at = datetime.now(UTC)

        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.boundary_type = "congressional"
        obj.district_identifier = "5"
        obj.full_name = "Nikema Williams"
        obj.first_name = "Nikema"
        obj.last_name = "Williams"
        obj.party = "Democratic"
        obj.title = "U.S. Representative"
        obj.photo_url = None
        obj.status = "approved"
        obj.created_at = datetime.now(UTC)
        obj.updated_at = datetime.now(UTC)
        obj.term_start_date = date(2023, 1, 3)
        obj.term_end_date = date(2025, 1, 3)
        obj.last_election_date = date(2022, 11, 8)
        obj.next_election_date = date(2024, 11, 5)
        obj.website = "https://williams.house.gov"
        obj.email = None
        obj.phone = None
        obj.office_address = None
        obj.external_ids = {"bioguide_id": "W000788"}
        obj.approved_by_id = None
        obj.approved_at = None
        obj.sources = [source_mock]

        resp = ElectedOfficialDetailResponse.model_validate(obj)
        assert resp.term_start_date == date(2023, 1, 3)
        assert resp.external_ids == {"bioguide_id": "W000788"}
        assert len(resp.sources) == 1
        assert resp.sources[0].source_name == "open_states"

    def test_empty_sources(self) -> None:
        """Detail response with no sources."""
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.boundary_type = "state_house"
        obj.district_identifier = "55"
        obj.full_name = "Jane Doe"
        obj.first_name = "Jane"
        obj.last_name = "Doe"
        obj.party = None
        obj.title = None
        obj.photo_url = None
        obj.status = "auto"
        obj.created_at = datetime.now(UTC)
        obj.updated_at = datetime.now(UTC)
        obj.term_start_date = None
        obj.term_end_date = None
        obj.last_election_date = None
        obj.next_election_date = None
        obj.website = None
        obj.email = None
        obj.phone = None
        obj.office_address = None
        obj.external_ids = None
        obj.approved_by_id = None
        obj.approved_at = None
        obj.sources = []

        resp = ElectedOfficialDetailResponse.model_validate(obj)
        assert resp.sources == []
        assert resp.status == "auto"


class TestPaginatedElectedOfficialResponse:
    """Tests for paginated response."""

    def test_construction(self) -> None:
        """Paginated response assembles correctly."""
        from voter_api.schemas.common import PaginationMeta

        resp = PaginatedElectedOfficialResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=0),
        )
        assert resp.items == []
        assert resp.pagination.total == 0


class TestApproveOfficialRequest:
    """Tests for ApproveOfficialRequest."""

    def test_default_no_source(self) -> None:
        """Defaults to no source promotion."""
        req = ApproveOfficialRequest()
        assert req.source_id is None

    def test_with_source_id(self) -> None:
        """Can specify a source to promote."""
        sid = uuid.uuid4()
        req = ApproveOfficialRequest(source_id=sid)
        assert req.source_id == sid


class TestElectedOfficialSourceResponse:
    """Tests for ElectedOfficialSourceResponse."""

    def test_from_attributes(self) -> None:
        """Schema hydrates from ORM-like object."""
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.source_name = "congress_gov"
        obj.source_record_id = "W000788"
        obj.boundary_type = "congressional"
        obj.district_identifier = "5"
        obj.full_name = "Nikema Williams"
        obj.first_name = "Nikema"
        obj.last_name = "Williams"
        obj.party = "Democratic"
        obj.title = "Representative"
        obj.photo_url = None
        obj.term_start_date = date(2023, 1, 3)
        obj.term_end_date = None
        obj.website = "https://williams.house.gov"
        obj.email = None
        obj.phone = None
        obj.office_address = None
        obj.fetched_at = datetime.now(UTC)
        obj.is_current = True
        obj.created_at = datetime.now(UTC)

        resp = ElectedOfficialSourceResponse.model_validate(obj)
        assert resp.source_name == "congress_gov"
        assert resp.is_current is True
        assert resp.term_start_date == date(2023, 1, 3)
