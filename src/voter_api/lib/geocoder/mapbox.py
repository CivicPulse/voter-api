"""Mapbox Geocoding API v6 provider.

Uses the Mapbox Geocoding API v6
(https://docs.mapbox.com/api/search/geocoding-v6/)
for address-to-coordinate resolution. Requires an access token.
"""

import httpx
from loguru import logger

from voter_api.lib.geocoder.base import (
    BaseGeocoder,
    GeocodeQuality,
    GeocodeServiceType,
    GeocodingProviderError,
    GeocodingResult,
)

MAPBOX_API_URL = "https://api.mapbox.com/search/geocode/v6/forward"
MAPBOX_BATCH_API_URL = "https://api.mapbox.com/search/geocode/v6/batch"
DEFAULT_TIMEOUT = 10.0
DEFAULT_BATCH_SIZE = 100


class MapboxGeocoder(BaseGeocoder):
    """Mapbox geocoder provider with batch support."""

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._batch_size = batch_size

    @property
    def provider_name(self) -> str:
        return "mapbox"

    @property
    def service_type(self) -> GeocodeServiceType:
        return GeocodeServiceType.BATCH

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode a single address using the Mapbox API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On transport or service errors.
        """
        params = {
            "q": address,
            "access_token": self._api_key,
            "country": "us",
            "limit": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(MAPBOX_API_URL, params=params)
                response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException as e:
            logger.warning("Mapbox geocoder timeout for address (redacted)")
            raise GeocodingProviderError("mapbox", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Mapbox geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "mapbox",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Mapbox geocoder connection error")
            raise GeocodingProviderError("mapbox", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Mapbox geocoder unexpected error")
            raise GeocodingProviderError("mapbox", f"Unexpected error: {e}") from e

    async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult | None]:
        """Geocode multiple addresses using Mapbox batch endpoint.

        Args:
            addresses: List of normalized address strings.

        Returns:
            List of GeocodingResult (or None for failures), same order as input.
        """
        all_results: list[GeocodingResult | None] = []

        for i in range(0, len(addresses), self._batch_size):
            chunk = addresses[i : i + self._batch_size]
            chunk_results = await self._batch_chunk(chunk)
            all_results.extend(chunk_results)

        return all_results

    async def _batch_chunk(self, addresses: list[str]) -> list[GeocodingResult | None]:
        """Geocode a single batch chunk via the Mapbox batch endpoint."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    MAPBOX_BATCH_API_URL,
                    params={"access_token": self._api_key},
                    json=[{"q": addr, "country": "us", "limit": 1} for addr in addresses],
                )
                response.raise_for_status()

            data = response.json()
            batch_results = data.get("batch", [])

            results: list[GeocodingResult | None] = []
            for entry in batch_results:
                results.append(self._parse_response(entry))

            return results

        except httpx.TimeoutException as e:
            logger.warning("Mapbox batch geocoder timeout")
            raise GeocodingProviderError("mapbox", "Batch geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Mapbox batch geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "mapbox",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Mapbox batch geocoder connection error")
            raise GeocodingProviderError("mapbox", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Mapbox batch geocoder unexpected error")
            raise GeocodingProviderError("mapbox", f"Unexpected error: {e}") from e

    def _parse_response(self, data: dict) -> GeocodingResult | None:
        """Parse Mapbox API response into a GeocodingResult."""
        features = data.get("features", [])
        if not features:
            return None

        best = features[0]
        try:
            coords = best["geometry"]["coordinates"]
            lng = float(coords[0])
            lat = float(coords[1])
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Mapbox response: {e}")
            raise GeocodingProviderError("mapbox", f"Failed to parse response: {e}") from e

        # Determine quality from match_code and feature type
        properties = best.get("properties", {})
        match_code = properties.get("match_code", {})
        confidence_level = match_code.get("confidence", "low")
        feature_type = properties.get("feature_type", "")

        quality = self._map_quality(feature_type, confidence_level)
        relevance = float(properties.get("relevance", 0.5))

        # Build matched address from full_address or name
        matched_address = properties.get("full_address") or properties.get("name")

        return GeocodingResult(
            latitude=lat,
            longitude=lng,
            confidence_score=min(relevance, 1.0),
            raw_response=data,
            matched_address=matched_address,
            quality=quality,
        )

    @staticmethod
    def _map_quality(feature_type: str, confidence: str) -> GeocodeQuality:
        """Map Mapbox feature type and confidence to GeocodeQuality."""
        if feature_type == "address" and confidence == "exact":
            return GeocodeQuality.EXACT
        if feature_type == "address":
            return GeocodeQuality.INTERPOLATED
        return GeocodeQuality.APPROXIMATE
