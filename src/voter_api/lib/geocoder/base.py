"""Abstract base geocoder interface for pluggable provider support."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GeocodingResult:
    """Result from a geocoding operation."""

    latitude: float
    longitude: float
    confidence_score: float | None = None
    raw_response: dict | None = None
    matched_address: str | None = None


class GeocodingProviderError(Exception):
    """Raised when a geocoding provider experiences a transport or service error.

    Distinguishes provider failures (timeout, HTTP error, connection error)
    from a successful response with no match (which returns None).

    Args:
        provider_name: Name of the failing provider.
        message: Human-readable error description.
        status_code: Optional HTTP status code from the provider.
    """

    def __init__(self, provider_name: str, message: str, status_code: int | None = None) -> None:
        self.provider_name = provider_name
        self.message = message
        self.status_code = status_code
        super().__init__(f"{provider_name}: {message}")


class BaseGeocoder(ABC):
    """Abstract geocoder interface. All providers must implement this."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique name identifying this geocoder provider."""

    @abstractmethod
    async def geocode(self, address: str) -> GeocodingResult | None:
        """Geocode a single address.

        Args:
            address: Full normalized address string.

        Returns:
            GeocodingResult or None if the address could not be geocoded.
        """

    async def batch_geocode(self, addresses: list[str]) -> list[GeocodingResult | None]:
        """Geocode multiple addresses.

        Default implementation calls geocode() sequentially.
        Providers may override for batch API support.

        Args:
            addresses: List of normalized address strings.

        Returns:
            List of GeocodingResult (or None for failures), same order as input.
        """
        results: list[GeocodingResult | None] = []
        for addr in addresses:
            results.append(await self.geocode(addr))
        return results
