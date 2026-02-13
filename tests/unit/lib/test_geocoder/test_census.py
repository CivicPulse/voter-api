"""Unit tests for Census Bureau geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodingProviderError
from voter_api.lib.geocoder.census import CensusGeocoder


class TestCensusResponseParsing:
    """Tests for Census API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = CensusGeocoder()

    def test_successful_match(self) -> None:
        """Successful address match returns GeocodingResult."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 N MAIN ST, ATLANTA, GA, 30301",
                        "coordinates": {"x": -84.3880, "y": 33.7490},
                        "tigerLine": {"tigerLineId": "12345"},
                    }
                ]
            }
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == 33.7490
        assert result.longitude == -84.3880
        assert result.confidence_score == 1.0
        assert result.matched_address == "123 N MAIN ST, ATLANTA, GA, 30301"

    def test_no_matches(self) -> None:
        """No matches returns None."""
        data = {"result": {"addressMatches": []}}
        assert self.geocoder._parse_response(data) is None

    def test_missing_coordinates(self) -> None:
        """Missing coordinates returns None."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST",
                        "coordinates": {},
                    }
                ]
            }
        }
        assert self.geocoder._parse_response(data) is None

    def test_malformed_response(self) -> None:
        """Malformed response returns None."""
        assert self.geocoder._parse_response({}) is None
        assert self.geocoder._parse_response({"result": {}}) is None

    def test_no_tigerline_lower_confidence(self) -> None:
        """Result without tigerLine gets lower confidence."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST",
                        "coordinates": {"x": -84.0, "y": 33.0},
                    }
                ]
            }
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.confidence_score == 0.8


class TestCensusGeocoderErrorDifferentiation:
    """Tests for CensusGeocoder error differentiation (US3)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_provider_error(self) -> None:
        """httpx.TimeoutException raises GeocodingProviderError."""
        geocoder = CensusGeocoder(timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="census") as exc_info,
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert exc_info.value.provider_name == "census"

    @pytest.mark.asyncio
    async def test_http_status_error_raises_provider_error(self) -> None:
        """httpx.HTTPStatusError raises GeocodingProviderError."""
        geocoder = CensusGeocoder()
        mock_response = httpx.Response(status_code=500, request=httpx.Request("GET", "http://test"))
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError) as exc_info,
        ):
            mock_get.side_effect = httpx.HTTPStatusError(
                "Server error", request=mock_response.request, response=mock_response
            )
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert exc_info.value.provider_name == "census"
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_connection_error_raises_provider_error(self) -> None:
        """Connection error raises GeocodingProviderError."""
        geocoder = CensusGeocoder()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError) as exc_info,
        ):
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert exc_info.value.provider_name == "census"

    @pytest.mark.asyncio
    async def test_empty_matches_returns_none(self) -> None:
        """Successful response with empty addressMatches returns None."""
        geocoder = CensusGeocoder()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"addressMatches": []}}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("99999 NONEXISTENT RD, NOWHERE, GA 00000")

        assert result is None

    @pytest.mark.asyncio
    async def test_successful_match_returns_result(self) -> None:
        """Successful response with matches returns GeocodingResult."""
        geocoder = CensusGeocoder()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST, ATLANTA, GA, 30303",
                        "coordinates": {"x": -84.388, "y": 33.749},
                        "tigerLine": {"tigerLineId": "12345"},
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.latitude == 33.749
        assert result.longitude == -84.388


class TestGetGeocoder:
    """Tests for geocoder provider registry."""

    def test_get_census(self) -> None:
        """Census geocoder is available by name."""
        from voter_api.lib.geocoder import get_geocoder

        geocoder = get_geocoder("census")
        assert geocoder.provider_name == "census"

    def test_unknown_provider(self) -> None:
        """Unknown provider raises ValueError."""
        import pytest

        from voter_api.lib.geocoder import get_geocoder

        with pytest.raises(ValueError, match="Unknown geocoder provider"):
            get_geocoder("nonexistent")
