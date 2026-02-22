"""Abstract base geocoder interface for pluggable provider support."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class GeocodeQuality(StrEnum):
    """Quality level of a geocoding result, from most to least precise."""

    EXACT = "exact"
    INTERPOLATED = "interpolated"
    APPROXIMATE = "approximate"
    NO_MATCH = "no_match"
    FAILED = "failed"


# Ranking for quality comparison (lower = better)
_QUALITY_RANK: dict[GeocodeQuality, int] = {
    GeocodeQuality.EXACT: 0,
    GeocodeQuality.INTERPOLATED: 1,
    GeocodeQuality.APPROXIMATE: 2,
    GeocodeQuality.NO_MATCH: 3,
    GeocodeQuality.FAILED: 4,
}


class GeocodeServiceType(StrEnum):
    """Whether a provider supports individual or batch geocoding natively."""

    INDIVIDUAL = "individual"
    BATCH = "batch"


@dataclass
class GeocodingResult:
    """Result from a geocoding operation."""

    latitude: float
    longitude: float
    confidence_score: float | None = None
    raw_response: dict | None = None
    matched_address: str | None = None
    quality: GeocodeQuality | None = None

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90):
            msg = f"latitude must be between -90 and 90, got {self.latitude}"
            raise ValueError(msg)
        if not (-180 <= self.longitude <= 180):
            msg = f"longitude must be between -180 and 180, got {self.longitude}"
            raise ValueError(msg)
        if self.confidence_score is not None and not (0 <= self.confidence_score <= 1):
            msg = f"confidence_score must be between 0 and 1, got {self.confidence_score}"
            raise ValueError(msg)


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

    @property
    def service_type(self) -> GeocodeServiceType:
        """Whether this provider supports batch or individual geocoding natively."""
        return GeocodeServiceType.INDIVIDUAL

    @property
    def requires_api_key(self) -> bool:
        """Whether this provider requires an API key to function."""
        return False

    @property
    def is_configured(self) -> bool:
        """Whether this provider has all required configuration (e.g., API keys)."""
        return True

    @property
    def rate_limit_delay(self) -> float:
        """Minimum delay in seconds between requests (for rate-limited providers)."""
        return 0.0

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
