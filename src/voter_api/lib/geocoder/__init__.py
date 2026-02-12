"""Geocoder library — pluggable address geocoding with caching.

Public API:
    - reconstruct_address: Build a full address from voter components
    - BaseGeocoder: Abstract provider interface
    - GeocodingResult: Result dataclass
    - CensusGeocoder: US Census Bureau provider
    - cache_lookup / cache_store: Database caching functions
    - get_geocoder: Provider factory/registry
"""

from voter_api.lib.geocoder.address import reconstruct_address
from voter_api.lib.geocoder.base import BaseGeocoder, GeocodingResult
from voter_api.lib.geocoder.cache import cache_lookup, cache_store
from voter_api.lib.geocoder.census import CensusGeocoder

# Provider registry
_PROVIDERS: dict[str, type[BaseGeocoder]] = {
    "census": CensusGeocoder,
}


def get_geocoder(provider: str = "census") -> BaseGeocoder:
    """Get a geocoder instance by provider name.

    Args:
        provider: Provider name (e.g., "census").

    Returns:
        An instance of the requested geocoder provider.

    Raises:
        ValueError: If the provider is not registered.
    """
    cls = _PROVIDERS.get(provider)
    if cls is None:
        msg = f"Unknown geocoder provider: {provider!r}. Available: {list(_PROVIDERS.keys())}"
        raise ValueError(msg)
    return cls()


__all__ = [
    "BaseGeocoder",
    "CensusGeocoder",
    "GeocodingResult",
    "cache_lookup",
    "cache_store",
    "get_geocoder",
    "reconstruct_address",
]
