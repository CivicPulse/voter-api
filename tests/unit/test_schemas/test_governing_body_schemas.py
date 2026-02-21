"""Unit tests for governing body Pydantic schemas."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.governing_body import (
    GoverningBodyCreateRequest,
    GoverningBodyDetailResponse,
    GoverningBodySummaryResponse,
    GoverningBodyUpdateRequest,
    PaginatedGoverningBodyResponse,
)


def _mock_type() -> MagicMock:
    """Create a mock GoverningBodyType for relationship."""
    t = MagicMock()
    t.id = uuid.uuid4()
    t.name = "County Commission"
    t.slug = "county-commission"
    t.description = None
    t.is_default = True
    t.created_at = datetime.now(UTC)
    return t


def _mock_body(**overrides) -> MagicMock:
    """Create a mock GoverningBody ORM object."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "Fulton County Commission",
        "type": _mock_type(),
        "jurisdiction": "Fulton County",
        "description": "County governing body",
        "website_url": "https://example.com",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestGoverningBodySummaryResponse:
    """Tests for GoverningBodySummaryResponse schema."""

    def test_from_attributes(self) -> None:
        """Summary can be hydrated from ORM object."""
        obj = _mock_body()
        resp = GoverningBodySummaryResponse.model_validate(obj)
        assert resp.id == obj.id
        assert resp.name == "Fulton County Commission"
        assert resp.jurisdiction == "Fulton County"
        assert resp.type.name == "County Commission"

    def test_optional_website_url(self) -> None:
        """website_url is optional."""
        obj = _mock_body(website_url=None)
        resp = GoverningBodySummaryResponse.model_validate(obj)
        assert resp.website_url is None


class TestGoverningBodyDetailResponse:
    """Tests for GoverningBodyDetailResponse schema."""

    def test_extends_summary(self) -> None:
        """Detail adds description, meeting_count, updated_at."""
        obj = _mock_body()
        resp = GoverningBodyDetailResponse.model_validate(obj)
        assert resp.description == "County governing body"
        assert resp.updated_at is not None

    def test_meeting_count_from_dict(self) -> None:
        """meeting_count defaults to 0 when constructed from dict without it."""
        data = {
            "id": uuid.uuid4(),
            "name": "Test",
            "type": {
                "id": uuid.uuid4(),
                "name": "County Commission",
                "slug": "county-commission",
                "description": None,
                "is_default": True,
                "created_at": datetime.now(UTC),
            },
            "jurisdiction": "Test County",
            "description": None,
            "website_url": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        resp = GoverningBodyDetailResponse(**data)
        assert resp.meeting_count == 0


class TestGoverningBodyCreateRequest:
    """Tests for GoverningBodyCreateRequest validation."""

    def test_valid_minimal(self) -> None:
        """Minimal create: name, type_id, jurisdiction."""
        req = GoverningBodyCreateRequest(
            name="Fulton County Commission",
            type_id=uuid.uuid4(),
            jurisdiction="Fulton County",
        )
        assert req.name == "Fulton County Commission"
        assert req.description is None
        assert req.website_url is None

    def test_valid_full(self) -> None:
        """Full create with all optional fields."""
        req = GoverningBodyCreateRequest(
            name="DeKalb County Commission",
            type_id=uuid.uuid4(),
            jurisdiction="DeKalb County",
            description="County governing body for DeKalb",
            website_url="https://dekalbcountyga.gov",
        )
        assert req.description is not None
        assert req.website_url is not None

    def test_missing_name_rejected(self) -> None:
        """Missing name is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                type_id=uuid.uuid4(),
                jurisdiction="Fulton County",
            )

    def test_missing_type_id_rejected(self) -> None:
        """Missing type_id is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                name="Test Body",
                jurisdiction="Test County",
            )

    def test_missing_jurisdiction_rejected(self) -> None:
        """Missing jurisdiction is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                name="Test Body",
                type_id=uuid.uuid4(),
            )

    def test_empty_name_rejected(self) -> None:
        """Empty string name is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                name="",
                type_id=uuid.uuid4(),
                jurisdiction="Test County",
            )

    def test_name_max_length(self) -> None:
        """Name exceeding 200 chars is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                name="x" * 201,
                type_id=uuid.uuid4(),
                jurisdiction="Test County",
            )

    def test_invalid_website_url_rejected(self) -> None:
        """Invalid URL is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyCreateRequest(
                name="Test Body",
                type_id=uuid.uuid4(),
                jurisdiction="Test County",
                website_url="not-a-url",
            )


class TestGoverningBodyUpdateRequest:
    """Tests for GoverningBodyUpdateRequest validation."""

    def test_all_fields_optional(self) -> None:
        """All fields are optional on update."""
        req = GoverningBodyUpdateRequest()
        assert req.name is None
        assert req.type_id is None
        assert req.jurisdiction is None
        assert req.description is None
        assert req.website_url is None

    def test_partial_update(self) -> None:
        """Only provided fields are set."""
        req = GoverningBodyUpdateRequest(name="Updated Name")
        data = req.model_dump(exclude_unset=True)
        assert "name" in data
        assert "jurisdiction" not in data

    def test_empty_name_rejected(self) -> None:
        """Empty name on update is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyUpdateRequest(name="")


class TestPaginatedGoverningBodyResponse:
    """Tests for PaginatedGoverningBodyResponse."""

    def test_structure(self) -> None:
        """Paginated response has items and pagination."""
        resp = PaginatedGoverningBodyResponse(
            items=[],
            pagination=PaginationMeta(
                total=0,
                page=1,
                page_size=20,
                total_pages=0,
            ),
        )
        assert resp.items == []
        assert resp.pagination.total == 0
