"""Unit tests for geocoder cache layer.

These tests verify the cache lookup/store function signatures and basic behavior.
Full integration tests with the database are in tests/integration/.
"""

from voter_api.lib.geocoder.base import GeocodingResult
from voter_api.lib.geocoder.cache import cache_lookup, cache_store


class TestCacheFunctions:
    """Tests that cache functions are importable and have correct signatures."""

    def test_cache_lookup_is_async(self) -> None:
        """cache_lookup is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(cache_lookup)

    def test_cache_store_is_async(self) -> None:
        """cache_store is an async function."""
        import asyncio

        assert asyncio.iscoroutinefunction(cache_store)

    def test_geocoding_result_creation(self) -> None:
        """GeocodingResult can be created with coordinates."""
        result = GeocodingResult(
            latitude=33.749,
            longitude=-84.388,
            confidence_score=0.95,
            raw_response={"test": True},
        )
        assert result.latitude == 33.749
        assert result.longitude == -84.388
        assert result.confidence_score == 0.95
        assert result.raw_response == {"test": True}

    def test_geocoding_result_defaults(self) -> None:
        """GeocodingResult has sensible defaults."""
        result = GeocodingResult(latitude=33.0, longitude=-84.0)
        assert result.confidence_score is None
        assert result.raw_response is None
        assert result.matched_address is None
