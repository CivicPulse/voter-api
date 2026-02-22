"""US Census Bureau geocoder provider.

Uses the Census Geocoding API (https://geocoding.geo.census.gov/geocoder/)
for address-to-coordinate resolution.
"""

import httpx
from loguru import logger

from voter_api.lib.geocoder.base import BaseGeocoder, GeocodeQuality, GeocodingProviderError, GeocodingResult

CENSUS_API_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
DEFAULT_TIMEOUT = 30.0


class CensusGeocoder(BaseGeocoder):
    """US Census Bureau geocoder provider."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "census"

    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode an address using the Census Bureau API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if the provider responded but found no match.

        Raises:
            GeocodingProviderError: On transport or service errors (timeout, HTTP error, connection).
        """
        params = {
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(CENSUS_API_URL, params=params)
                response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException as e:
            logger.warning("Census geocoder timeout for address (redacted)")
            raise GeocodingProviderError("census", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Census geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "census", f"Provider returned HTTP {e.response.status_code}", status_code=e.response.status_code
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Census geocoder connection error")
            raise GeocodingProviderError("census", "Connection to geocoding provider failed") from e
        except Exception as e:
            logger.exception("Census geocoder unexpected error")
            raise GeocodingProviderError("census", f"Unexpected error: {e}") from e

    def _parse_response(self, data: dict) -> GeocodingResult | None:
        """Parse Census API response into a GeocodingResult.

        Args:
            data: Raw JSON response from Census API.

        Returns:
            GeocodingResult or None if no match found.
        """
        try:
            result = data.get("result", {})
            matches = result.get("addressMatches", [])

            if not matches:
                return None

            best = matches[0]
            coords = best.get("coordinates", {})
            lon = coords.get("x")
            lat = coords.get("y")

            if lat is None or lon is None:
                return None

            matched_address = best.get("matchedAddress")
            has_tiger_line = bool(best.get("tigerLine"))

            return GeocodingResult(
                latitude=float(lat),
                longitude=float(lon),
                confidence_score=1.0 if has_tiger_line else 0.8,
                raw_response=data,
                matched_address=matched_address,
                quality=GeocodeQuality.EXACT if has_tiger_line else GeocodeQuality.INTERPOLATED,
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Census geocoder response: {e}")
            raise GeocodingProviderError("census", f"Failed to parse response: {e}") from e
