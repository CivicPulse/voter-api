"""Unit tests for governing body type service layer."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from voter_api.services.governing_body_type_service import (
    _generate_slug,
    create_type,
    list_types,
)


def _mock_session(scalars_all_value=None) -> AsyncMock:
    """Create a mock async session with configurable return values."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = scalars_all_value or []
    session.execute.return_value = mock_result
    return session


def _mock_type(**overrides) -> MagicMock:
    """Create a mock GoverningBodyType."""
    defaults = {
        "id": uuid.uuid4(),
        "name": "County Commission",
        "slug": "county-commission",
        "description": None,
        "is_default": True,
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestGenerateSlug:
    """Tests for slug generation helper."""

    def test_simple_name(self) -> None:
        assert _generate_slug("County Commission") == "county-commission"

    def test_special_characters_stripped(self) -> None:
        assert _generate_slug("Water & Power Authority") == "water-power-authority"

    def test_extra_spaces_collapsed(self) -> None:
        assert _generate_slug("  Transit   Authority  ") == "transit-authority"

    def test_already_slug(self) -> None:
        assert _generate_slug("city-council") == "city-council"


class TestListTypes:
    """Tests for list_types."""

    @pytest.mark.asyncio
    async def test_returns_all_types(self) -> None:
        """Returns all governing body types ordered by name."""
        types = [_mock_type(name="A"), _mock_type(name="B")]
        session = _mock_session(scalars_all_value=types)
        result = await list_types(session)
        assert len(result) == 2
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list(self) -> None:
        """Returns empty list when no types exist."""
        session = _mock_session()
        result = await list_types(session)
        assert result == []


class TestCreateType:
    """Tests for create_type."""

    @pytest.mark.asyncio
    async def test_creates_with_generated_slug(self) -> None:
        """Creates a type with auto-generated slug."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        await create_type(session, name="Water Authority", description="Manages water")
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert added_obj.slug == "water-authority"
        assert added_obj.is_default is False

    @pytest.mark.asyncio
    async def test_duplicate_name_raises_value_error(self) -> None:
        """Duplicate name/slug raises ValueError."""
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock(side_effect=IntegrityError("", {}, Exception()))
        session.rollback = AsyncMock()
        with pytest.raises(ValueError, match="already exists"):
            await create_type(session, name="County Commission")
