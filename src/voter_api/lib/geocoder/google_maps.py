"""Google Maps Geocoding API provider.

Uses the Google Maps Geocoding API
(https://developers.google.com/maps/documentation/geocoding/)
for address-to-coordinate resolution. Requires an API key.
"""

import httpx
from loguru import logger

from voter_api.lib.geocoder.base import (
    BaseGeocoder,
    GeocodeQuality,
    GeocodingProviderError,
    GeocodingResult,
)

GOOGLE_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DEFAULT_TIMEOUT = 10.0

# Google location_type → (quality, confidence)
_LOCATION_TYPE_MAP: dict[str, tuple[GeocodeQuality, float]] = {
    "ROOFTOP": (GeocodeQuality.EXACT, 1.0),
    "RANGE_INTERPOLATED": (GeocodeQuality.INTERPOLATED, 0.85),
    "GEOMETRIC_CENTER": (GeocodeQuality.APPROXIMATE, 0.6),
    "APPROXIMATE": (GeocodeQuality.APPROXIMATE, 0.5),
}


class GoogleMapsGeocoder(BaseGeocoder):
    """Google Maps geocoder provider."""

    def __init__(
        self,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        region: str = "us",
    ) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._region = region

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode an address using the Google Maps API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On transport, service, or API-specific errors.
        """
        params = {
            "address": address,
            "key": self._api_key,
            "region": self._region,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(GOOGLE_API_URL, params=params)
                response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException as e:
            logger.warning("Google Maps geocoder timeout for address (redacted)")
            raise GeocodingProviderError("google", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Google Maps geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "google",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Google Maps geocoder connection error")
            raise GeocodingProviderError("google", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Google Maps geocoder unexpected error")
            raise GeocodingProviderError("google", f"Unexpected error: {e}") from e

    def _parse_response(self, data: dict) -> GeocodingResult | None:
        """Parse Google Maps API response into a GeocodingResult.

        Args:
            data: Raw JSON response from Google Maps API.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On API-specific error statuses.
        """
        api_status = data.get("status", "UNKNOWN")

        if api_status == "ZERO_RESULTS":
            return None

        if api_status in ("REQUEST_DENIED", "OVER_QUERY_LIMIT", "INVALID_REQUEST"):
            msg = data.get("error_message", api_status)
            raise GeocodingProviderError("google", f"API error: {msg}")

        if api_status != "OK":
            raise GeocodingProviderError("google", f"Unexpected API status: {api_status}")

        results = data.get("results", [])
        if not results:
            return None

        best = results[0]
        try:
            location = best["geometry"]["location"]
            lat = float(location["lat"])
            lng = float(location["lng"])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Google Maps response: {e}")
            raise GeocodingProviderError("google", f"Failed to parse response: {e}") from e

        location_type = best.get("geometry", {}).get("location_type", "APPROXIMATE")
        quality, confidence = _LOCATION_TYPE_MAP.get(
            location_type,
            (GeocodeQuality.APPROXIMATE, 0.5),
        )

        return GeocodingResult(
            latitude=lat,
            longitude=lng,
            confidence_score=confidence,
            raw_response=data,
            matched_address=best.get("formatted_address"),
            quality=quality,
        )
