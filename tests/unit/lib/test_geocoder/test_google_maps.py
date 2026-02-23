"""Unit tests for Google Maps geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodingProviderError
from voter_api.lib.geocoder.google_maps import GoogleMapsGeocoder


class TestGoogleMapsResponseParsing:
    """Tests for Google Maps API response parsing."""

    def setup_method(self) -> None:
        self.geocoder: GoogleMapsGeocoder = GoogleMapsGeocoder(api_key="test-key")

    def test_successful_rooftop_match(self) -> None:
        data = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "123 Main St, Atlanta, GA 30301",
                    "geometry": {
                        "location": {"lat": 33.749, "lng": -84.388},
                        "location_type": "ROOFTOP",
                    },
                }
            ],
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == pytest.approx(33.749)
        assert result.longitude == pytest.approx(-84.388)
        assert result.quality == GeocodeQuality.EXACT
        assert result.confidence_score == pytest.approx(1.0)
        assert result.matched_address == "123 Main St, Atlanta, GA 30301"

    def test_range_interpolated(self) -> None:
        data = {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {"lat": 33.0, "lng": -84.0},
                        "location_type": "RANGE_INTERPOLATED",
                    },
                }
            ],
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.INTERPOLATED
        assert result.confidence_score == pytest.approx(0.85)

    def test_geometric_center(self) -> None:
        data = {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {"lat": 33.0, "lng": -84.0},
                        "location_type": "GEOMETRIC_CENTER",
                    },
                }
            ],
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE
        assert result.confidence_score == pytest.approx(0.6)

    def test_zero_results(self) -> None:
        data = {"status": "ZERO_RESULTS"}
        assert self.geocoder._parse_response(data) is None

    def test_request_denied_raises(self) -> None:
        data = {"status": "REQUEST_DENIED", "error_message": "Invalid API key"}
        with pytest.raises(GeocodingProviderError, match="API error"):
            self.geocoder._parse_response(data)

    def test_over_query_limit_raises(self) -> None:
        data = {"status": "OVER_QUERY_LIMIT", "error_message": "Quota exceeded"}
        with pytest.raises(GeocodingProviderError, match="API error"):
            self.geocoder._parse_response(data)

    def test_unknown_status_raises(self) -> None:
        data = {"status": "UNKNOWN_ERROR"}
        with pytest.raises(GeocodingProviderError, match="Unexpected API status"):
            self.geocoder._parse_response(data)

    def test_empty_results_returns_none(self) -> None:
        data = {"status": "OK", "results": []}
        assert self.geocoder._parse_response(data) is None

    def test_missing_geometry_raises(self) -> None:
        data = {
            "status": "OK",
            "results": [{"formatted_address": "test"}],
        }
        with pytest.raises(GeocodingProviderError, match="Failed to parse"):
            self.geocoder._parse_response(data)


class TestGoogleMapsGeocoderErrors:
    """Tests for GoogleMapsGeocoder error differentiation."""

    async def test_timeout_raises_provider_error(self) -> None:
        geocoder = GoogleMapsGeocoder(api_key="test-key", timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="google"),
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_connection_error_raises_provider_error(self) -> None:
        geocoder = GoogleMapsGeocoder(api_key="test-key")
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="google"),
        ):
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_successful_geocode(self) -> None:
        geocoder = GoogleMapsGeocoder(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "123 Main St, Atlanta, GA 30301",
                    "geometry": {
                        "location": {"lat": 33.749, "lng": -84.388},
                        "location_type": "ROOFTOP",
                    },
                }
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.quality == GeocodeQuality.EXACT


class TestGoogleMapsProperties:
    """Tests for GoogleMapsGeocoder base properties."""

    def test_provider_name(self) -> None:
        assert GoogleMapsGeocoder(api_key="key").provider_name == "google"

    def test_requires_api_key(self) -> None:
        assert GoogleMapsGeocoder(api_key="key").requires_api_key is True

    def test_is_configured_with_key(self) -> None:
        assert GoogleMapsGeocoder(api_key="valid-key").is_configured is True

    def test_is_not_configured_without_key(self) -> None:
        assert GoogleMapsGeocoder(api_key="").is_configured is False
