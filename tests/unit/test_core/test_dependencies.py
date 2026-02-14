"""Tests for FastAPI dependency injection module."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from voter_api.core.dependencies import filter_by_sensitivity, require_role
from voter_api.core.sensitivity import SensitivityTier


class TestRequireRole:
    """Tests for require_role factory."""

    @pytest.mark.asyncio
    async def test_admin_role_passes(self) -> None:
        checker = require_role("admin")
        user = MagicMock()
        user.role = "admin"

        result = await checker(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_multiple_allowed_roles(self) -> None:
        checker = require_role("admin", "analyst")
        user = MagicMock()
        user.role = "analyst"

        result = await checker(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_insufficient_role_raises_403(self) -> None:
        checker = require_role("admin")
        user = MagicMock()
        user.role = "viewer"

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403
        assert "viewer" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_viewer_rejected_from_admin_only(self) -> None:
        checker = require_role("admin")
        user = MagicMock()
        user.role = "viewer"

        with pytest.raises(HTTPException) as exc_info:
            await checker(current_user=user)
        assert exc_info.value.status_code == 403


class TestFilterBySensitivity:
    """Tests for filter_by_sensitivity."""

    def test_admin_sees_all_fields(self) -> None:
        data = {"field_a": "value_a", "field_b": "value_b"}
        result = filter_by_sensitivity(data, "admin", MagicMock)
        assert result == data

    def test_analyst_sees_all_fields(self) -> None:
        data = {"field_a": "value_a", "field_b": "value_b"}
        result = filter_by_sensitivity(data, "analyst", MagicMock)
        assert result == data

    def test_viewer_filters_system_generated_fields(self) -> None:
        from pydantic import BaseModel, Field

        class TestSchema(BaseModel):
            public_field: str = Field(default="")
            system_field: str = Field(
                default="",
                json_schema_extra={"sensitivity_tier": SensitivityTier.SYSTEM_GENERATED.value},
            )

        data = {"public_field": "visible", "system_field": "hidden"}
        result = filter_by_sensitivity(data, "viewer", TestSchema)
        assert "public_field" in result
        assert result["public_field"] == "visible"
        assert "system_field" not in result

    def test_viewer_with_no_metadata_includes_field(self) -> None:
        from pydantic import BaseModel

        class SimpleSchema(BaseModel):
            name: str = ""

        data = {"name": "test"}
        result = filter_by_sensitivity(data, "viewer", SimpleSchema)
        assert result["name"] == "test"
