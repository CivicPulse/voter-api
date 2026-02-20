"""Geocoder library — pluggable address geocoding with caching.

Public API:
    - reconstruct_address: Build a full address from voter components
    - normalize_freeform_address: Normalize a freeform address string
    - parse_address_components: Parse freeform string into components
    - AddressComponents: Parsed address component dataclass
    - validate_address_components: Validate parsed components for completeness
    - validate_georgia_coordinates: Validate coords are in Georgia
    - meters_to_degrees: Convert meters to degrees at a latitude
    - BaseGeocoder: Abstract provider interface
    - GeocodingResult: Result dataclass
    - CensusGeocoder: US Census Bureau provider
    - cache_lookup / cache_store: Database caching functions
    - get_geocoder: Provider factory/registry
    - BaseSuggestionSource: Abstract interface for suggestion providers
"""

from typing import Any

from voter_api.lib.geocoder.address import (
    AddressComponents,
    normalize_freeform_address,
    parse_address_components,
    reconstruct_address,
)
from voter_api.lib.geocoder.base import BaseGeocoder, GeocodingProviderError, GeocodingResult
from voter_api.lib.geocoder.cache import cache_lookup, cache_store
from voter_api.lib.geocoder.census import CensusGeocoder
from voter_api.lib.geocoder.point_lookup import (
    meters_to_degrees,
    validate_georgia_coordinates,
)
from voter_api.lib.geocoder.verify import BaseSuggestionSource, validate_address_components

# Provider registry
_PROVIDERS: dict[str, type[BaseGeocoder]] = {
    "census": CensusGeocoder,
}


def get_available_providers() -> list[str]:
    """Return the names of all registered geocoder providers.

    Returns:
        Sorted list of provider name strings.
    """
    return sorted(_PROVIDERS.keys())


def get_geocoder(provider: str = "census", **kwargs: Any) -> BaseGeocoder:
    """Get a geocoder instance by provider name.

    Args:
        provider: Provider name (e.g., "census").
        **kwargs: Additional arguments forwarded to the provider constructor
            (e.g., ``timeout=2.0``).

    Returns:
        An instance of the requested geocoder provider.

    Raises:
        ValueError: If the provider is not registered.
    """
    cls = _PROVIDERS.get(provider)
    if cls is None:
        msg = f"Unknown geocoder provider: {provider!r}. Available: {list(_PROVIDERS.keys())}"
        raise ValueError(msg)
    return cls(**kwargs)


__all__ = [
    "AddressComponents",
    "BaseGeocoder",
    "BaseSuggestionSource",
    "GeocodingProviderError",
    "CensusGeocoder",
    "GeocodingResult",
    "cache_lookup",
    "cache_store",
    "get_available_providers",
    "get_geocoder",
    "meters_to_degrees",
    "normalize_freeform_address",
    "parse_address_components",
    "reconstruct_address",
    "validate_address_components",
    "validate_georgia_coordinates",
]
