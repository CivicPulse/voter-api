"""Unit tests for governing body type Pydantic schemas."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from voter_api.schemas.governing_body_type import (
    GoverningBodyTypeCreateRequest,
    GoverningBodyTypeResponse,
)


class TestGoverningBodyTypeResponse:
    """Tests for GoverningBodyTypeResponse schema."""

    def test_from_attributes(self) -> None:
        """Response can be hydrated from an ORM-like object."""
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.name = "County Commission"
        obj.slug = "county-commission"
        obj.description = "A county-level commission"
        obj.is_default = True
        obj.created_at = datetime.now(UTC)

        resp = GoverningBodyTypeResponse.model_validate(obj)
        assert resp.id == obj.id
        assert resp.name == "County Commission"
        assert resp.slug == "county-commission"
        assert resp.description == "A county-level commission"
        assert resp.is_default is True

    def test_optional_description(self) -> None:
        """Description field is optional (None)."""
        obj = MagicMock()
        obj.id = uuid.uuid4()
        obj.name = "City Council"
        obj.slug = "city-council"
        obj.description = None
        obj.is_default = False
        obj.created_at = datetime.now(UTC)

        resp = GoverningBodyTypeResponse.model_validate(obj)
        assert resp.description is None


class TestGoverningBodyTypeCreateRequest:
    """Tests for GoverningBodyTypeCreateRequest validation."""

    def test_valid_minimal(self) -> None:
        """Name only (description optional)."""
        req = GoverningBodyTypeCreateRequest(name="Water Authority")
        assert req.name == "Water Authority"
        assert req.description is None

    def test_valid_with_description(self) -> None:
        """Name + description."""
        req = GoverningBodyTypeCreateRequest(
            name="Transit Authority",
            description="Public transit governance body",
        )
        assert req.description == "Public transit governance body"

    def test_name_required(self) -> None:
        """Missing name is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyTypeCreateRequest()

    def test_empty_name_rejected(self) -> None:
        """Empty string name is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            GoverningBodyTypeCreateRequest(name="")

    def test_name_max_length(self) -> None:
        """Name exceeding 100 chars is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyTypeCreateRequest(name="x" * 101)

    def test_description_max_length(self) -> None:
        """Description exceeding 500 chars is rejected."""
        with pytest.raises(ValidationError):
            GoverningBodyTypeCreateRequest(name="Valid", description="x" * 501)
