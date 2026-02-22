"""OpenStreetMap Nominatim geocoder provider.

Uses the Nominatim API (https://nominatim.org/release-docs/develop/api/Search/)
for address-to-coordinate resolution. Free but rate-limited to 1 req/sec.
"""

import httpx
from loguru import logger

from voter_api.lib.geocoder.base import (
    BaseGeocoder,
    GeocodeQuality,
    GeocodingProviderError,
    GeocodingResult,
)

NOMINATIM_API_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_TIMEOUT = 10.0
DEFAULT_USER_AGENT = "voter-api/1.0"


class NominatimGeocoder(BaseGeocoder):
    """OpenStreetMap Nominatim geocoder provider."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        email: str = "",
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._timeout = timeout
        self._email = email
        self._user_agent = user_agent

    @property
    def provider_name(self) -> str:
        return "nominatim"

    @property
    def rate_limit_delay(self) -> float:
        return 1.0

    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode an address using the Nominatim API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On transport or service errors.
        """
        params: dict[str, str | int] = {
            "q": address,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
            "countrycodes": "us",
        }
        if self._email:
            params["email"] = self._email

        headers = {"User-Agent": self._user_agent}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(NOMINATIM_API_URL, params=params, headers=headers)
                response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException as e:
            logger.warning("Nominatim geocoder timeout for address (redacted)")
            raise GeocodingProviderError("nominatim", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Nominatim geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "nominatim",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Nominatim geocoder connection error")
            raise GeocodingProviderError("nominatim", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Nominatim geocoder unexpected error")
            raise GeocodingProviderError("nominatim", f"Unexpected error: {e}") from e

    def _parse_response(self, data: list[dict]) -> GeocodingResult | None:
        """Parse Nominatim API response into a GeocodingResult.

        Args:
            data: Raw JSON response (list of results) from Nominatim API.

        Returns:
            GeocodingResult or None if no match found.
        """
        if not data:
            return None

        best = data[0]
        try:
            lat = float(best["lat"])
            lon = float(best["lon"])
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Nominatim response: {e}")
            raise GeocodingProviderError("nominatim", f"Failed to parse response: {e}") from e

        importance = float(best.get("importance", 0.0))
        quality = self._map_quality(importance)
        confidence = min(importance, 1.0)

        return GeocodingResult(
            latitude=lat,
            longitude=lon,
            confidence_score=confidence,
            raw_response={"results": data},
            matched_address=best.get("display_name"),
            quality=quality,
        )

    @staticmethod
    def _map_quality(importance: float) -> GeocodeQuality:
        """Map Nominatim importance score to GeocodeQuality."""
        if importance >= 0.8:
            return GeocodeQuality.EXACT
        if importance >= 0.5:
            return GeocodeQuality.INTERPOLATED
        return GeocodeQuality.APPROXIMATE
