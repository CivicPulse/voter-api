"""Geocodio geocoder provider.

Uses the Geocodio API (https://www.geocod.io/docs/) for address-to-coordinate
resolution. Requires an API key. Supports native batch geocoding.
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

GEOCODIO_API_URL = "https://api.geocod.io/v1.7/geocode"
DEFAULT_TIMEOUT = 30.0
DEFAULT_BATCH_SIZE = 1000

# Geocodio accuracy_type → quality mapping
_ACCURACY_MAP: dict[str, GeocodeQuality] = {
    "rooftop": GeocodeQuality.EXACT,
    "point": GeocodeQuality.EXACT,
    "range_interpolation": GeocodeQuality.INTERPOLATED,
    "nearest_rooftop_match": GeocodeQuality.INTERPOLATED,
    "street_center": GeocodeQuality.APPROXIMATE,
    "nearest_street": GeocodeQuality.APPROXIMATE,
    "place": GeocodeQuality.APPROXIMATE,
    "state": GeocodeQuality.APPROXIMATE,
}


class GeocodioGeocoder(BaseGeocoder):
    """Geocodio geocoder provider with native batch support."""

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
        return "geocodio"

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
        """Geocode a single address using the Geocodio API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On transport or service errors.
        """
        params = {
            "q": address,
            "api_key": self._api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(GEOCODIO_API_URL, params=params)
                response.raise_for_status()

            data = response.json()
            results = data.get("results", [])
            if not results:
                return None

            return self._parse_single_result(results[0], data)

        except httpx.TimeoutException as e:
            logger.warning("Geocodio geocoder timeout for address (redacted)")
            raise GeocodingProviderError("geocodio", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Geocodio geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "geocodio",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Geocodio geocoder connection error")
            raise GeocodingProviderError("geocodio", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Geocodio geocoder unexpected error")
            raise GeocodingProviderError("geocodio", f"Unexpected error: {e}") from e

    async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult | None]:
        """Geocode multiple addresses using Geocodio's native batch endpoint.

        Args:
            addresses: List of normalized address strings.

        Returns:
            List of GeocodingResult (or None for failures), same order as input.

        Raises:
            GeocodingProviderError: On transport or service errors.
        """
        all_results: list[GeocodingResult | None] = []

        for i in range(0, len(addresses), self._batch_size):
            chunk = addresses[i : i + self._batch_size]
            chunk_results = await self._batch_chunk(chunk)
            all_results.extend(chunk_results)

        return all_results

    async def _batch_chunk(self, addresses: list[str]) -> list[GeocodingResult | None]:
        """Geocode a single batch chunk via POST."""
        params = {"api_key": self._api_key}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(GEOCODIO_API_URL, params=params, json=addresses)
                response.raise_for_status()

            data = response.json()
            batch_results = data.get("results", [])

            results: list[GeocodingResult | None] = []
            for entry in batch_results:
                response_data = entry.get("response", {})
                inner_results = response_data.get("results", [])
                if inner_results:
                    results.append(self._parse_single_result(inner_results[0], response_data))
                else:
                    results.append(None)

            return results

        except httpx.TimeoutException as e:
            logger.warning("Geocodio batch geocoder timeout")
            raise GeocodingProviderError("geocodio", "Batch geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Geocodio batch geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "geocodio",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Geocodio batch geocoder connection error")
            raise GeocodingProviderError("geocodio", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Geocodio batch geocoder unexpected error")
            raise GeocodingProviderError("geocodio", f"Unexpected error: {e}") from e

    def _parse_single_result(self, result: dict, raw: dict) -> GeocodingResult | None:
        """Parse a single Geocodio result into a GeocodingResult."""
        try:
            location = result.get("location", {})
            lat = float(location["lat"])
            lng = float(location["lng"])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Geocodio response: {e}")
            raise GeocodingProviderError("geocodio", f"Failed to parse response: {e}") from e

        accuracy = result.get("accuracy")
        accuracy_type = result.get("accuracy_type", "")
        quality = _ACCURACY_MAP.get(accuracy_type, GeocodeQuality.APPROXIMATE)

        # Geocodio accuracy is 0-1 scale
        confidence = float(accuracy) if accuracy is not None else 0.5

        return GeocodingResult(
            latitude=lat,
            longitude=lng,
            confidence_score=min(confidence, 1.0),
            raw_response=raw,
            matched_address=result.get("formatted_address"),
            quality=quality,
        )
