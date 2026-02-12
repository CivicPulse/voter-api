"""Unit tests for common Pydantic schemas."""

import pytest
from pydantic import ValidationError

from voter_api.schemas.common import ErrorResponse, PaginationMeta, PaginationParams


class TestPaginationParams:
    """Tests for PaginationParams validation."""

    def test_defaults(self) -> None:
        """Default page and page_size are applied."""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20

    def test_valid_values(self) -> None:
        """Valid values are accepted."""
        params = PaginationParams(page=3, page_size=50)
        assert params.page == 3
        assert params.page_size == 50

    def test_page_zero_rejected(self) -> None:
        """Page 0 is rejected."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_page_size_over_max_rejected(self) -> None:
        """Page size over 100 is rejected."""
        with pytest.raises(ValidationError):
            PaginationParams(page_size=101)


class TestPaginationMeta:
    """Tests for PaginationMeta."""

    def test_construction(self) -> None:
        """PaginationMeta holds correct values."""
        meta = PaginationMeta(total=100, page=2, page_size=20, total_pages=5)
        assert meta.total == 100
        assert meta.total_pages == 5


class TestErrorResponse:
    """Tests for ErrorResponse."""

    def test_minimal(self) -> None:
        """ErrorResponse with only detail field."""
        err = ErrorResponse(detail="Not found")
        assert err.detail == "Not found"
        assert err.code is None
        assert err.errors is None

    def test_full(self) -> None:
        """ErrorResponse with all fields."""
        err = ErrorResponse(detail="Validation failed", code="VALIDATION_ERROR", errors=[{"field": "name"}])
        assert err.code == "VALIDATION_ERROR"
        assert len(err.errors) == 1
