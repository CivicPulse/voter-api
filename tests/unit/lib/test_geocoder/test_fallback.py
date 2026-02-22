"""Unit tests for geocode_with_fallback() cascading logic."""

from unittest.mock import AsyncMock, patch

import pytest

from voter_api.lib.geocoder.base import (
    BaseGeocoder,
    GeocodeQuality,
    GeocodingProviderError,
    GeocodingResult,
)
from voter_api.services.geocoding_service import geocode_with_fallback


class MockGeocoder(BaseGeocoder):
    """Test geocoder that returns a pre-configured result."""

    def __init__(self, name: str, result: GeocodingResult | None = None, error: bool = False) -> None:
        self._name = name
        self._result = result
        self._error = error

    @property
    def provider_name(self) -> str:
        return self._name

    async def geocode(self, address: str) -> GeocodingResult | None:
        if self._error:
            raise GeocodingProviderError(self._name, "Test error")
        return self._result


def _result(quality: GeocodeQuality, confidence: float = 0.8) -> GeocodingResult:
    return GeocodingResult(
        latitude=33.75,
        longitude=-84.39,
        confidence_score=confidence,
        quality=quality,
    )


class TestGeocodeWithFallback:
    """Tests for geocode_with_fallback() cascading logic."""

    @pytest.mark.asyncio
    async def test_exact_stops_immediately(self) -> None:
        """EXACT result from first provider stops cascading."""
        p1 = MockGeocoder("provider_a", _result(GeocodeQuality.EXACT, 0.9))
        p2 = MockGeocoder("provider_b", _result(GeocodeQuality.EXACT, 1.0))

        with (
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ),
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is not None
        assert result[0] == "provider_a"
        assert result[1].quality == GeocodeQuality.EXACT

    @pytest.mark.asyncio
    async def test_non_exact_tries_all_picks_best(self) -> None:
        """Non-EXACT results collect and pick the best."""
        p1 = MockGeocoder("provider_a", _result(GeocodeQuality.APPROXIMATE, 0.5))
        p2 = MockGeocoder("provider_b", _result(GeocodeQuality.INTERPOLATED, 0.8))

        with (
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ),
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is not None
        assert result[0] == "provider_b"
        assert result[1].quality == GeocodeQuality.INTERPOLATED

    @pytest.mark.asyncio
    async def test_skip_erroring_providers(self) -> None:
        """Providers that raise errors are skipped, not fatal."""
        p1 = MockGeocoder("failing", error=True)
        p2 = MockGeocoder("working", _result(GeocodeQuality.INTERPOLATED, 0.7))

        with (
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ),
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is not None
        assert result[0] == "working"

    @pytest.mark.asyncio
    async def test_all_fail_returns_none(self) -> None:
        """All providers failing returns None."""
        p1 = MockGeocoder("fail_a", error=True)
        p2 = MockGeocoder("fail_b", error=True)

        with patch(
            "voter_api.services.geocoding_service.cache_lookup",
            new_callable=AsyncMock,
            return_value=None,
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self) -> None:
        """Providers returning None are skipped."""
        p1 = MockGeocoder("no_match_a", result=None)
        p2 = MockGeocoder("no_match_b", result=None)

        with patch(
            "voter_api.services.geocoding_service.cache_lookup",
            new_callable=AsyncMock,
            return_value=None,
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is None

    @pytest.mark.asyncio
    async def test_empty_providers_returns_none(self) -> None:
        session = AsyncMock()
        result = await geocode_with_fallback(session, "test addr", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_cached_exact_stops(self) -> None:
        """EXACT result from cache stops cascading."""
        cached = GeocodingResult(
            latitude=33.75,
            longitude=-84.39,
            confidence_score=0.9,
            quality=GeocodeQuality.EXACT,
        )
        p1 = MockGeocoder("cached_provider")
        p2 = MockGeocoder("other", _result(GeocodeQuality.EXACT, 1.0))

        with patch(
            "voter_api.services.geocoding_service.cache_lookup",
            new_callable=AsyncMock,
            return_value=cached,
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is not None
        assert result[0] == "cached_provider"

    @pytest.mark.asyncio
    async def test_cached_non_exact_continues(self) -> None:
        """Non-EXACT cache hit continues to try other providers."""
        cached = GeocodingResult(
            latitude=33.75,
            longitude=-84.39,
            confidence_score=0.5,
            quality=GeocodeQuality.APPROXIMATE,
        )
        p1 = MockGeocoder("cached_provider")
        p2 = MockGeocoder("better", _result(GeocodeQuality.INTERPOLATED, 0.8))

        # Return cached for p1, None for p2
        async def side_effect(session, provider, address):
            if provider == "cached_provider":
                return cached
            return None

        with (
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                side_effect=side_effect,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ),
        ):
            session = AsyncMock()
            result = await geocode_with_fallback(session, "test addr", [p1, p2])

        assert result is not None
        assert result[0] == "better"
        assert result[1].quality == GeocodeQuality.INTERPOLATED
