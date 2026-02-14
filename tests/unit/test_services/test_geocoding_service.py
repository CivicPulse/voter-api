"""Unit tests for geocoding service — geocode_single_address, _geocode_with_retry, get_cache_stats."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.lib.geocoder.base import GeocodingProviderError, GeocodingResult
from voter_api.schemas.geocoding import CacheProviderStats
from voter_api.services.geocoding_service import (
    _geocode_with_retry,
    geocode_single_address,
    get_cache_stats,
)


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_geocoding_result(**overrides):
    """Create a GeocodingResult with Georgia defaults."""
    defaults = {
        "latitude": 33.749,
        "longitude": -84.388,
        "confidence_score": 1.0,
        "raw_response": {"test": True},
        "matched_address": "123 MAIN ST, ATLANTA, GA 30303",
    }
    defaults.update(overrides)
    return GeocodingResult(**defaults)


class TestGeocodeSingleAddress:
    """Tests for geocode_single_address()."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_result(self, mock_session) -> None:
        """Cache hit returns AddressGeocodeResponse with cached=True."""
        cached_result = _make_geocoding_result()

        with (
            patch(
                "voter_api.services.geocoding_service.normalize_freeform_address",
                return_value="123 MAIN ST ATLANTA GA 30303",
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=cached_result,
            ),
            patch("voter_api.services.geocoding_service.validate_georgia_coordinates"),
        ):
            result = await geocode_single_address(mock_session, "123 Main St, Atlanta, GA 30303")

        assert result is not None
        assert result.metadata.cached is True
        assert result.latitude == 33.749

    @pytest.mark.asyncio
    async def test_cache_miss_calls_provider(self, mock_session) -> None:
        """Cache miss calls geocoder provider and stores result."""
        geo_result = _make_geocoding_result()
        address_mock = MagicMock()
        address_mock.id = uuid.uuid4()

        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(return_value=geo_result)

        with (
            patch(
                "voter_api.services.geocoding_service.normalize_freeform_address",
                return_value="123 MAIN ST ATLANTA GA 30303",
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            patch("voter_api.services.geocoding_service.validate_georgia_coordinates"),
            patch("voter_api.services.geocoding_service.parse_address_components") as mock_parse,
            patch(
                "voter_api.services.geocoding_service.upsert_from_geocode",
                new_callable=AsyncMock,
                return_value=address_mock,
            ),
            patch(
                "voter_api.services.geocoding_service.cache_store",
                new_callable=AsyncMock,
            ) as mock_cache_store,
        ):
            mock_parse.return_value.to_dict.return_value = {"street_name": "MAIN"}
            result = await geocode_single_address(mock_session, "123 Main St, Atlanta, GA 30303")

        assert result is not None
        assert result.metadata.cached is False
        mock_cache_store.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provider_no_match_returns_none(self, mock_session) -> None:
        """Provider returning None (no match) returns None."""
        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(return_value=None)

        with (
            patch(
                "voter_api.services.geocoding_service.normalize_freeform_address",
                return_value="99999 FAKE RD NOWHERE GA 00000",
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
        ):
            result = await geocode_single_address(mock_session, "99999 Fake Rd, Nowhere, GA 00000")

        assert result is None

    @pytest.mark.asyncio
    async def test_provider_error_raises_after_retries(self, mock_session) -> None:
        """GeocodingProviderError propagates after retry attempts exhausted."""
        mock_geocoder = AsyncMock()
        mock_geocoder.provider_name = "census"
        mock_geocoder.geocode = AsyncMock(side_effect=GeocodingProviderError("census", "timeout"))

        with (
            patch(
                "voter_api.services.geocoding_service.normalize_freeform_address",
                return_value="123 MAIN ST ATLANTA GA 30303",
            ),
            patch(
                "voter_api.services.geocoding_service.cache_lookup",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "voter_api.services.geocoding_service.get_geocoder",
                return_value=mock_geocoder,
            ),
            pytest.raises(GeocodingProviderError),
        ):
            await geocode_single_address(mock_session, "123 Main St, Atlanta, GA 30303")

    @pytest.mark.asyncio
    async def test_empty_normalization_returns_none(self, mock_session) -> None:
        """Empty normalized address returns None."""
        with patch(
            "voter_api.services.geocoding_service.normalize_freeform_address",
            return_value="",
        ):
            result = await geocode_single_address(mock_session, "")

        assert result is None


class TestGeocodeWithRetry:
    """Tests for _geocode_with_retry()."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """Successful geocode on first attempt returns result."""
        geo_result = _make_geocoding_result()
        mock_geocoder = AsyncMock()
        mock_geocoder.geocode = AsyncMock(return_value=geo_result)
        semaphore = asyncio.Semaphore(5)

        result = await _geocode_with_retry(mock_geocoder, "123 MAIN ST", semaphore)

        assert result is not None
        assert result.latitude == 33.749
        mock_geocoder.geocode.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_match_returns_none_without_retry(self) -> None:
        """Provider returning None (no match) returns None immediately."""
        mock_geocoder = AsyncMock()
        mock_geocoder.geocode = AsyncMock(return_value=None)
        semaphore = asyncio.Semaphore(5)

        result = await _geocode_with_retry(mock_geocoder, "99999 FAKE RD", semaphore)

        assert result is None
        # Should not retry on genuine no-match
        mock_geocoder.geocode.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_then_success(self) -> None:
        """Provider error then success returns result."""
        geo_result = _make_geocoding_result()
        mock_geocoder = AsyncMock()
        mock_geocoder.geocode = AsyncMock(
            side_effect=[
                GeocodingProviderError("census", "timeout"),
                geo_result,
            ]
        )
        semaphore = asyncio.Semaphore(5)

        with patch("voter_api.services.geocoding_service.RETRY_BASE_DELAY", 0):
            result = await _geocode_with_retry(mock_geocoder, "123 MAIN ST", semaphore)

        assert result is not None
        assert mock_geocoder.geocode.await_count == 2

    @pytest.mark.asyncio
    async def test_exhaustion_raises_provider_error(self) -> None:
        """All retries exhausted with provider errors raises GeocodingProviderError."""
        mock_geocoder = AsyncMock()
        mock_geocoder.geocode = AsyncMock(side_effect=GeocodingProviderError("census", "timeout"))
        semaphore = asyncio.Semaphore(5)

        with (
            patch("voter_api.services.geocoding_service.RETRY_BASE_DELAY", 0),
            pytest.raises(GeocodingProviderError, match="timeout"),
        ):
            await _geocode_with_retry(mock_geocoder, "123 MAIN ST", semaphore)


class TestGetCacheStats:
    """Tests for get_cache_stats()."""

    @pytest.mark.asyncio
    async def test_returns_typed_cache_provider_stats(self, mock_session) -> None:
        """Returns list of CacheProviderStats objects."""
        mock_row = MagicMock()
        mock_row.provider = "census"
        mock_row.cached_count = 42
        mock_row.oldest_entry = None
        mock_row.newest_entry = None

        mock_result = MagicMock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        stats = await get_cache_stats(mock_session)

        assert len(stats) == 1
        assert isinstance(stats[0], CacheProviderStats)
        assert stats[0].provider == "census"
        assert stats[0].cached_count == 42
