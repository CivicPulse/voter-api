"""Unit tests for Photon (Komoot) geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodingProviderError
from voter_api.lib.geocoder.photon import PhotonGeocoder


class TestPhotonResponseParsing:
    """Tests for Photon API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = PhotonGeocoder()

    def test_successful_house_match(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [-84.388, 33.749]},
                    "properties": {
                        "type": "house",
                        "housenumber": "123",
                        "street": "Main St",
                        "city": "Atlanta",
                        "state": "Georgia",
                        "postcode": "30301",
                    },
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == 33.749
        assert result.longitude == -84.388
        assert result.quality == GeocodeQuality.EXACT
        assert result.confidence_score == 0.95
        assert "123 Main St" in result.matched_address

    def test_street_level_match(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {"type": "street", "street": "Main St"},
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.INTERPOLATED
        assert result.confidence_score == 0.7

    def test_city_level_match(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {"type": "city", "name": "Atlanta"},
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE
        assert result.confidence_score == 0.3

    def test_building_type_exact(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {"type": "building", "name": "City Hall"},
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.EXACT

    def test_no_features(self) -> None:
        assert self.geocoder._parse_response({"features": []}) is None
        assert self.geocoder._parse_response({}) is None

    def test_missing_geometry_raises(self) -> None:
        data = {"features": [{"properties": {"type": "house"}}]}
        with pytest.raises(GeocodingProviderError, match="photon"):
            self.geocoder._parse_response(data)

    def test_unknown_type_approximate(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {"type": "unknown_osm_type"},
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE


class TestPhotonBuildAddress:
    """Tests for Photon address building from properties."""

    def test_full_address(self) -> None:
        props = {
            "housenumber": "123",
            "street": "Main St",
            "city": "Atlanta",
            "state": "Georgia",
            "postcode": "30301",
        }
        result = PhotonGeocoder._build_address(props)
        assert result == "123 Main St, Atlanta, Georgia, 30301"

    def test_street_only(self) -> None:
        props = {"street": "Main St"}
        result = PhotonGeocoder._build_address(props)
        assert result == "Main St"

    def test_empty_properties(self) -> None:
        assert PhotonGeocoder._build_address({}) is None

    def test_name_included(self) -> None:
        props = {"name": "Atlanta City Hall", "city": "Atlanta"}
        result = PhotonGeocoder._build_address(props)
        assert result == "Atlanta City Hall, Atlanta"


class TestPhotonGeocoderErrors:
    """Tests for PhotonGeocoder error differentiation."""

    @pytest.mark.asyncio
    async def test_timeout_raises_provider_error(self) -> None:
        geocoder = PhotonGeocoder(timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="photon"),
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    @pytest.mark.asyncio
    async def test_connection_error_raises_provider_error(self) -> None:
        geocoder = PhotonGeocoder()
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="photon"),
        ):
            mock_get.side_effect = httpx.ConnectError("Connection refused")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    @pytest.mark.asyncio
    async def test_successful_geocode(self) -> None:
        geocoder = PhotonGeocoder()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.388, 33.749]},
                    "properties": {"type": "house", "name": "123 Main St"},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.quality == GeocodeQuality.EXACT

    @pytest.mark.asyncio
    async def test_custom_base_url(self) -> None:
        geocoder = PhotonGeocoder(base_url="https://my-photon.example.com")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"features": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
            await geocoder.geocode("test")

        # Verify it used the custom base URL
        call_args = mock_get.call_args
        assert "my-photon.example.com" in str(call_args)


class TestPhotonProperties:
    """Tests for PhotonGeocoder base properties."""

    def test_provider_name(self) -> None:
        assert PhotonGeocoder().provider_name == "photon"

    def test_requires_api_key(self) -> None:
        assert PhotonGeocoder().requires_api_key is False

    def test_is_configured(self) -> None:
        assert PhotonGeocoder().is_configured is True

    def test_rate_limit_delay_default(self) -> None:
        assert PhotonGeocoder().rate_limit_delay == 0.0
