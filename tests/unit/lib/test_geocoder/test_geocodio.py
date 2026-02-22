"""Unit tests for Geocodio geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodeServiceType, GeocodingProviderError
from voter_api.lib.geocoder.geocodio import GeocodioGeocoder


class TestGeocodioResponseParsing:
    """Tests for Geocodio API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = GeocodioGeocoder(api_key="test-key")

    def test_successful_rooftop_match(self) -> None:
        result_data = {
            "location": {"lat": 33.749, "lng": -84.388},
            "accuracy": 1.0,
            "accuracy_type": "rooftop",
            "formatted_address": "123 Main St, Atlanta, GA 30301",
        }
        raw = {"results": [result_data]}
        result = self.geocoder._parse_single_result(result_data, raw)
        assert result is not None
        assert result.latitude == 33.749
        assert result.longitude == -84.388
        assert result.quality == GeocodeQuality.EXACT
        assert result.confidence_score == 1.0

    def test_range_interpolation_quality(self) -> None:
        result_data = {
            "location": {"lat": 33.0, "lng": -84.0},
            "accuracy": 0.8,
            "accuracy_type": "range_interpolation",
        }
        result = self.geocoder._parse_single_result(result_data, {})
        assert result is not None
        assert result.quality == GeocodeQuality.INTERPOLATED

    def test_street_center_quality(self) -> None:
        result_data = {
            "location": {"lat": 33.0, "lng": -84.0},
            "accuracy": 0.5,
            "accuracy_type": "street_center",
        }
        result = self.geocoder._parse_single_result(result_data, {})
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE

    def test_unknown_accuracy_type(self) -> None:
        result_data = {
            "location": {"lat": 33.0, "lng": -84.0},
            "accuracy": 0.3,
            "accuracy_type": "unknown_type",
        }
        result = self.geocoder._parse_single_result(result_data, {})
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE

    def test_missing_location_raises(self) -> None:
        result_data = {"accuracy": 1.0}
        with pytest.raises(GeocodingProviderError, match="geocodio"):
            self.geocoder._parse_single_result(result_data, {})


class TestGeocodioGeocoderErrors:
    """Tests for GeocodioGeocoder error differentiation."""

    async def test_timeout_raises_provider_error(self) -> None:
        geocoder = GeocodioGeocoder(api_key="test-key", timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="geocodio"),
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_successful_geocode(self) -> None:
        geocoder = GeocodioGeocoder(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "location": {"lat": 33.749, "lng": -84.388},
                    "accuracy": 1.0,
                    "accuracy_type": "rooftop",
                    "formatted_address": "123 Main St, Atlanta, GA 30301",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.quality == GeocodeQuality.EXACT

    async def test_empty_results_returns_none(self) -> None:
        geocoder = GeocodioGeocoder(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("99999 NONEXISTENT RD")

        assert result is None


class TestGeocodioBatchGeocode:
    """Tests for Geocodio batch geocoding."""

    async def test_batch_geocode(self) -> None:
        geocoder = GeocodioGeocoder(api_key="test-key", batch_size=2)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "response": {
                        "results": [
                            {
                                "location": {"lat": 33.749, "lng": -84.388},
                                "accuracy": 1.0,
                                "accuracy_type": "rooftop",
                                "formatted_address": "123 Main St",
                            }
                        ]
                    }
                },
                {"response": {"results": []}},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            results = await geocoder.batch_geocode(["addr1", "addr2"])

        assert len(results) == 2
        assert results[0] is not None
        assert results[0].latitude == 33.749
        assert results[1] is None

    async def test_batch_timeout_raises(self) -> None:
        geocoder = GeocodioGeocoder(api_key="test-key")
        with (
            patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
            pytest.raises(GeocodingProviderError, match="geocodio"),
        ):
            mock_post.side_effect = httpx.TimeoutException("Timeout")
            await geocoder.batch_geocode(["addr1"])


class TestGeocodioProperties:
    """Tests for GeocodioGeocoder base properties."""

    def test_provider_name(self) -> None:
        assert GeocodioGeocoder(api_key="key").provider_name == "geocodio"

    def test_service_type_batch(self) -> None:
        assert GeocodioGeocoder(api_key="key").service_type == GeocodeServiceType.BATCH

    def test_requires_api_key(self) -> None:
        assert GeocodioGeocoder(api_key="key").requires_api_key is True

    def test_is_configured_with_key(self) -> None:
        assert GeocodioGeocoder(api_key="valid-key").is_configured is True

    def test_is_not_configured_without_key(self) -> None:
        assert GeocodioGeocoder(api_key="").is_configured is False
