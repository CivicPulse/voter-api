"""Unit tests for Mapbox geocoder provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodeServiceType, GeocodingProviderError
from voter_api.lib.geocoder.mapbox import MapboxGeocoder


class TestMapboxResponseParsing:
    """Tests for Mapbox API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = MapboxGeocoder(api_key="test-key")

    def test_successful_exact_match(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [-84.388, 33.749]},
                    "properties": {
                        "full_address": "123 Main St, Atlanta, GA 30301",
                        "feature_type": "address",
                        "match_code": {"confidence": "exact"},
                        "relevance": 0.95,
                    },
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == pytest.approx(33.749)
        assert result.longitude == pytest.approx(-84.388)
        assert result.quality == GeocodeQuality.EXACT
        assert result.confidence_score == pytest.approx(0.95)
        assert result.matched_address == "123 Main St, Atlanta, GA 30301"

    def test_interpolated_address(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {
                        "feature_type": "address",
                        "match_code": {"confidence": "high"},
                        "relevance": 0.8,
                    },
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.INTERPOLATED

    def test_non_address_feature_approximate(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {
                        "feature_type": "place",
                        "match_code": {"confidence": "medium"},
                        "relevance": 0.5,
                    },
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.quality == GeocodeQuality.APPROXIMATE

    def test_no_features(self) -> None:
        assert self.geocoder._parse_response({"features": []}) is None
        assert self.geocoder._parse_response({}) is None

    def test_missing_geometry_raises(self) -> None:
        data = {"features": [{"properties": {}}]}
        with pytest.raises(GeocodingProviderError, match="mapbox"):
            self.geocoder._parse_response(data)

    def test_name_fallback_for_address(self) -> None:
        data = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.0, 33.0]},
                    "properties": {
                        "name": "Some Place",
                        "feature_type": "place",
                        "relevance": 0.5,
                    },
                }
            ]
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.matched_address == "Some Place"


class TestMapboxQualityMapping:
    """Tests for Mapbox quality mapping logic."""

    def test_address_exact(self) -> None:
        assert MapboxGeocoder._map_quality("address", "exact") == GeocodeQuality.EXACT

    def test_address_non_exact(self) -> None:
        assert MapboxGeocoder._map_quality("address", "high") == GeocodeQuality.INTERPOLATED
        assert MapboxGeocoder._map_quality("address", "medium") == GeocodeQuality.INTERPOLATED

    def test_non_address(self) -> None:
        assert MapboxGeocoder._map_quality("place", "exact") == GeocodeQuality.APPROXIMATE
        assert MapboxGeocoder._map_quality("poi", "high") == GeocodeQuality.APPROXIMATE


class TestMapboxGeocoderErrors:
    """Tests for MapboxGeocoder error differentiation."""

    async def test_timeout_raises_provider_error(self) -> None:
        geocoder = MapboxGeocoder(api_key="test-key", timeout=0.1)
        with (
            patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
            pytest.raises(GeocodingProviderError, match="mapbox"),
        ):
            mock_get.side_effect = httpx.TimeoutException("Connection timed out")
            await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

    async def test_successful_geocode(self) -> None:
        geocoder = MapboxGeocoder(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "features": [
                {
                    "geometry": {"coordinates": [-84.388, 33.749]},
                    "properties": {
                        "full_address": "123 Main St, Atlanta, GA 30301",
                        "feature_type": "address",
                        "match_code": {"confidence": "exact"},
                        "relevance": 0.95,
                    },
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            result = await geocoder.geocode("123 MAIN ST, ATLANTA, GA 30303")

        assert result is not None
        assert result.quality == GeocodeQuality.EXACT


class TestMapboxBatchGeocode:
    """Tests for Mapbox batch geocoding."""

    async def test_batch_geocode(self) -> None:
        geocoder = MapboxGeocoder(api_key="test-key", batch_size=2)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "batch": [
                {
                    "features": [
                        {
                            "geometry": {"coordinates": [-84.388, 33.749]},
                            "properties": {
                                "full_address": "123 Main St",
                                "feature_type": "address",
                                "match_code": {"confidence": "exact"},
                                "relevance": 0.95,
                            },
                        }
                    ]
                },
                {"features": []},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            results = await geocoder.batch_geocode(["addr1", "addr2"])

        assert len(results) == 2
        assert results[0] is not None
        assert results[1] is None


class TestMapboxProperties:
    """Tests for MapboxGeocoder base properties."""

    def test_provider_name(self) -> None:
        assert MapboxGeocoder(api_key="key").provider_name == "mapbox"

    def test_service_type_batch(self) -> None:
        assert MapboxGeocoder(api_key="key").service_type == GeocodeServiceType.BATCH

    def test_requires_api_key(self) -> None:
        assert MapboxGeocoder(api_key="key").requires_api_key is True

    def test_is_configured_with_key(self) -> None:
        assert MapboxGeocoder(api_key="valid-key").is_configured is True

    def test_is_not_configured_without_key(self) -> None:
        assert MapboxGeocoder(api_key="").is_configured is False
