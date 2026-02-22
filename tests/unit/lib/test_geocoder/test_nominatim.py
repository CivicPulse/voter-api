"""Unit tests for Nominatim geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodingProviderError
from voter_api.lib.geocoder.nominatim import NominatimGeocoder


class TestNominatimResponseParsing:
    """Tests for Nominatim API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = NominatimGeocoder()

    def test_successful_match(self) -> None:
        data = [
            {
                "lat": "33.7490",
                "lon": "-84.3880",
                "display_name": "123 N Main St, Atlanta, GA",
                "importance": 0.85,
            }
        ]
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == 33.7490
        assert result.longitude == -84.3880
        assert result.quality == GeocodeQuality.EXACT
        assert result.confidence_score == 0.85
        assert result.matched_address == "123 N Main St, Atlanta, GA"

    def test_no_results(self) -> None:
        assert self.geocoder._parse_response([]) is None

    def test_low_importance_approximate(self) -> None:
        data = [{"lat": "33.0", "lon": "-84.0", "importance": 0.3}]
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE

    def test_medium_importance_interpolated(self) -> None:
        data = [{"lat": "33.0", "lon": "-84.0", "importance": 0.6}]
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.INTERPOLATED

    def test_missing_lat_raises(self) -> None:
        data = [{"lon": "-84.0", "importance": 0.5}]
        with pytest.raises(GeocodingProviderError, match="nominatim"):
            self.geocoder._parse_response(data)

    def test_malformed_coords_raises(self) -> None:
        data = [{"lat": "not-a-number", "lon": "-84.0"}]
        with pytest.raises(GeocodingProviderError, match="nominatim"):
            self.geocoder._parse_response(data)


class TestNominatimQualityMapping:
    """Tests for Nominatim importance → quality mapping."""

    def test_exact_threshold(self) -> None:
        assert NominatimGeocoder._map_quality(0.8) == GeocodeQuality.EXACT
        assert NominatimGeocoder._map_quality(1.0) == GeocodeQuality.EXACT

    def test_interpolated_threshold(self) -> None:
        assert NominatimGeocoder._map_quality(0.5) == GeocodeQuality.INTERPOLATED
        assert NominatimGeocoder._map_quality(0.79) == GeocodeQuality.INTERPOLATED

    def test_approximate_threshold(self) -> None:
        assert NominatimGeocoder._map_quality(0.0) == GeocodeQuality.APPROXIMATE
        assert NominatimGeocoder._map_quality(0.49) == GeocodeQuality.APPROXIMATE


class TestNominatimGeocoderErrors:
    """Tests for NominatimGeocoder error differentiation."""

    async def test_timeout_raises_provider_error(self) -> None:
        geocoder = NominatimGeocoder(timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="nominatim"),
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_http_error_raises_provider_error(self) -> None:
        geocoder = NominatimGeocoder()
        mock_response = httpx.Response(status_code=429, request=httpx.Request("GET", "http://test"))
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError) as exc_info,
        ):
            mock_get.side_effect = httpx.HTTPStatusError(
                "Rate limited", request=mock_response.request, response=mock_response
            )
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")
        assert exc_info.value.status_code == 429

    async def test_connection_error_raises_provider_error(self) -> None:
        geocoder = NominatimGeocoder()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="nominatim"),
        ):
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_successful_match_returns_result(self) -> None:
        geocoder = NominatimGeocoder()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "lat": "33.749",
                "lon": "-84.388",
                "display_name": "123 Main St, Atlanta, GA",
                "importance": 0.9,
            }
        ]
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.latitude == 33.749

    async def test_empty_results_returns_none(self) -> None:
        geocoder = NominatimGeocoder()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("99999 NONEXISTENT RD")

        assert result is None


class TestNominatimProperties:
    """Tests for NominatimGeocoder base properties."""

    def test_provider_name(self) -> None:
        assert NominatimGeocoder().provider_name == "nominatim"

    def test_rate_limit_delay(self) -> None:
        assert NominatimGeocoder().rate_limit_delay == 1.0

    def test_requires_api_key(self) -> None:
        assert NominatimGeocoder().requires_api_key is False

    def test_is_configured(self) -> None:
        assert NominatimGeocoder().is_configured is True
