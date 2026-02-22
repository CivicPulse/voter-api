"""Photon (Komoot) geocoder provider.

Uses the Photon geocoder (https://photon.komoot.io/) for address-to-coordinate
resolution. Free, open-source, and self-hostable. Based on OpenStreetMap data.
"""

import httpx
from loguru import logger

from voter_api.lib.geocoder.base import (
    BaseGeocoder,
    GeocodeQuality,
    GeocodingProviderError,
    GeocodingResult,
)

DEFAULT_BASE_URL = "https://photon.komoot.io"
DEFAULT_TIMEOUT = 10.0

# OSM type → quality mapping
_TYPE_QUALITY_MAP: dict[str, GeocodeQuality] = {
    "house": GeocodeQuality.EXACT,
    "building": GeocodeQuality.EXACT,
    "street": GeocodeQuality.INTERPOLATED,
    "locality": GeocodeQuality.APPROXIMATE,
    "district": GeocodeQuality.APPROXIMATE,
    "city": GeocodeQuality.APPROXIMATE,
    "county": GeocodeQuality.APPROXIMATE,
    "state": GeocodeQuality.APPROXIMATE,
    "country": GeocodeQuality.APPROXIMATE,
}

# Confidence scores by OSM type specificity
_TYPE_CONFIDENCE: dict[str, float] = {
    "house": 0.95,
    "building": 0.90,
    "street": 0.7,
    "locality": 0.5,
    "district": 0.4,
    "city": 0.3,
    "county": 0.2,
    "state": 0.1,
    "country": 0.05,
}


class PhotonGeocoder(BaseGeocoder):
    """Photon (Komoot) geocoder provider."""

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "photon"

    @property
    def rate_limit_delay(self) -> float:
        """Minimum delay between requests (public Photon has undocumented rate limits)."""
        return 0.2 if self._base_url == DEFAULT_BASE_URL else 0.0

    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode an address using the Photon API.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if no match found.

        Raises:
            GeocodingProviderError: On transport or service errors.
        """
        url = f"{self._base_url}/api"
        params: dict[str, str | int] = {
            "q": address,
            "limit": 1,
            "lang": "en",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()

            data = response.json()
            return self._parse_response(data)

        except httpx.TimeoutException as e:
            logger.warning("Photon geocoder timeout for address (redacted)")
            raise GeocodingProviderError("photon", "Geocoding request timed out") from e
        except httpx.HTTPStatusError as e:
            logger.warning(f"Photon geocoder HTTP error {e.response.status_code}")
            raise GeocodingProviderError(
                "photon",
                f"Provider returned HTTP {e.response.status_code}",
                status_code=e.response.status_code,
            ) from e
        except httpx.ConnectError as e:
            logger.warning("Photon geocoder connection error")
            raise GeocodingProviderError("photon", "Connection to geocoding provider failed") from e
        except GeocodingProviderError:
            raise
        except Exception as e:
            logger.exception("Photon geocoder unexpected error")
            raise GeocodingProviderError("photon", f"Unexpected error: {e}") from e

    def _parse_response(self, data: dict) -> GeocodingResult | None:
        """Parse Photon API response into a GeocodingResult.

        Args:
            data: Raw GeoJSON response from Photon API.

        Returns:
            GeocodingResult or None if no match found.
        """
        features = data.get("features", [])
        if not features:
            return None

        best = features[0]
        try:
            coords = best["geometry"]["coordinates"]
            lng = float(coords[0])
            lat = float(coords[1])
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse Photon response: {e}")
            raise GeocodingProviderError("photon", f"Failed to parse response: {e}") from e

        properties = best.get("properties", {})
        osm_type = properties.get("type", "")
        quality = _TYPE_QUALITY_MAP.get(osm_type, GeocodeQuality.APPROXIMATE)
        confidence = _TYPE_CONFIDENCE.get(osm_type, 0.3)

        # Build matched address from properties
        matched_address = self._build_address(properties)

        return GeocodingResult(
            latitude=lat,
            longitude=lng,
            confidence_score=confidence,
            raw_response=data,
            matched_address=matched_address,
            quality=quality,
        )

    @staticmethod
    def _build_address(properties: dict) -> str | None:
        """Build a human-readable address from Photon properties."""
        parts = []
        if properties.get("name"):
            parts.append(properties["name"])
        if properties.get("street"):
            street = properties["street"]
            if properties.get("housenumber"):
                street = f"{properties['housenumber']} {street}"
            parts.append(street)
        if properties.get("city"):
            parts.append(properties["city"])
        if properties.get("state"):
            parts.append(properties["state"])
        if properties.get("postcode"):
            parts.append(properties["postcode"])

        return ", ".join(parts) if parts else None
