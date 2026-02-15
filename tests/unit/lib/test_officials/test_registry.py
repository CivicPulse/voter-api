"""Unit tests for the officials provider registry."""

from unittest.mock import patch

import pytest

from voter_api.lib.officials import get_provider, register_provider
from voter_api.lib.officials.base import BaseOfficialsProvider, OfficialRecord


class _StubProvider(BaseOfficialsProvider):
    """Stub provider for testing the registry."""

    @property
    def provider_name(self) -> str:
        return "stub"

    async def fetch_by_district(self, boundary_type: str, district_identifier: str) -> list[OfficialRecord]:
        return []


class _StubProvider2(BaseOfficialsProvider):
    """Second stub provider for overwrite test."""

    @property
    def provider_name(self) -> str:
        return "stub2"

    async def fetch_by_district(self, boundary_type: str, district_identifier: str) -> list[OfficialRecord]:
        return []


class TestProviderRegistry:
    """Tests for get_provider / register_provider."""

    def test_unknown_provider_raises(self) -> None:
        """Requesting an unregistered provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown officials provider"):
            get_provider("nonexistent_provider")

    def test_register_and_get(self) -> None:
        """Registering a provider makes it retrievable."""
        register_provider("stub", _StubProvider)
        provider = get_provider("stub")
        assert provider.provider_name == "stub"

    def test_register_overwrites_with_warning(self) -> None:
        """Re-registering a provider logs a warning."""
        register_provider("overwrite_test", _StubProvider)
        with patch("voter_api.lib.officials.logger") as mock_logger:
            register_provider("overwrite_test", _StubProvider2)
            mock_logger.warning.assert_called_once()
            assert "overwrite_test" in mock_logger.warning.call_args[0][0]
        # The new provider should be in place
        provider = get_provider("overwrite_test")
        assert provider.provider_name == "stub2"
