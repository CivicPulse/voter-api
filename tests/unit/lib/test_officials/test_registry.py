"""Unit tests for the officials provider registry."""

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
