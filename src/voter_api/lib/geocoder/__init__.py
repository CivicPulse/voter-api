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
    - GeocodeQuality: Quality level enum
    - GeocodeServiceType: Service type enum
    - CensusGeocoder: US Census Bureau provider
    - NominatimGeocoder: OpenStreetMap Nominatim provider
    - GoogleMapsGeocoder: Google Maps provider
    - GeocodioGeocoder: Geocodio provider
    - MapboxGeocoder: Mapbox provider
    - PhotonGeocoder: Photon (Komoot) provider
    - cache_lookup / cache_store: Database caching functions
    - get_geocoder: Provider factory/registry
    - get_configured_providers: Get providers that are enabled and configured
    - BaseSuggestionSource: Abstract interface for suggestion providers
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from voter_api.lib.geocoder.address import (
    AddressComponents,
    normalize_freeform_address,
    parse_address_components,
    reconstruct_address,
)
from voter_api.lib.geocoder.base import (
    QUALITY_RANK,
    BaseGeocoder,
    GeocodeQuality,
    GeocodeServiceType,
    GeocodingProviderError,
    GeocodingResult,
)
from voter_api.lib.geocoder.cache import cache_lookup, cache_store
from voter_api.lib.geocoder.census import CensusGeocoder
from voter_api.lib.geocoder.geocodio import GeocodioGeocoder
from voter_api.lib.geocoder.google_maps import GoogleMapsGeocoder
from voter_api.lib.geocoder.mapbox import MapboxGeocoder
from voter_api.lib.geocoder.nominatim import NominatimGeocoder
from voter_api.lib.geocoder.photon import PhotonGeocoder
from voter_api.lib.geocoder.point_lookup import (
    meters_to_degrees,
    validate_georgia_coordinates,
)
from voter_api.lib.geocoder.verify import BaseSuggestionSource, validate_address_components

if TYPE_CHECKING:
    from voter_api.core.config import Settings

# Provider registry — all known providers
_PROVIDERS: dict[str, type[BaseGeocoder]] = {
    "census": CensusGeocoder,
    "nominatim": NominatimGeocoder,
    "google": GoogleMapsGeocoder,
    "geocodio": GeocodioGeocoder,
    "mapbox": MapboxGeocoder,
    "photon": PhotonGeocoder,
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


def get_configured_providers(settings: Settings) -> list[BaseGeocoder]:
    """Get geocoder instances for all providers that are enabled and properly configured.

    Reads per-provider enabled flags and config from settings, instantiates
    each provider with its settings, and returns only those that are both
    enabled and have required configuration (e.g., API keys).

    Args:
        settings: Application settings.

    Returns:
        List of configured BaseGeocoder instances, in fallback order.
    """
    provider_configs: dict[str, dict[str, Any]] = {
        "census": {
            "enabled": True,  # Always enabled
        },
        "nominatim": {
            "enabled": settings.geocoder_nominatim_enabled,
            "kwargs": {
                "timeout": settings.geocoder_nominatim_timeout,
                "email": settings.geocoder_nominatim_email,
            },
        },
        "google": {
            "enabled": settings.geocoder_google_enabled and bool(settings.geocoder_google_api_key),
            "kwargs": {
                "api_key": settings.geocoder_google_api_key or "",
                "timeout": settings.geocoder_google_timeout,
            },
        },
        "geocodio": {
            "enabled": settings.geocoder_geocodio_enabled and bool(settings.geocoder_geocodio_api_key),
            "kwargs": {
                "api_key": settings.geocoder_geocodio_api_key or "",
                "timeout": settings.geocoder_geocodio_timeout,
                "batch_size": settings.geocoder_geocodio_batch_size,
            },
        },
        "mapbox": {
            "enabled": settings.geocoder_mapbox_enabled and bool(settings.geocoder_mapbox_api_key),
            "kwargs": {
                "api_key": settings.geocoder_mapbox_api_key or "",
                "timeout": settings.geocoder_mapbox_timeout,
                "batch_size": settings.geocoder_mapbox_batch_size,
            },
        },
        "photon": {
            "enabled": settings.geocoder_photon_enabled,
            "kwargs": {
                "timeout": settings.geocoder_photon_timeout,
                "base_url": settings.geocoder_photon_base_url,
            },
        },
    }

    # Return in fallback order, filtered to enabled + configured (deduplicated)
    fallback_order = settings.geocoder_fallback_order_list
    providers: list[BaseGeocoder] = []
    seen: set[str] = set()

    for name in fallback_order:
        if name in seen:
            continue
        seen.add(name)
        config = provider_configs.get(name)
        if config is None or not config.get("enabled", False):
            continue

        kwargs = config.get("kwargs", {})
        try:
            geocoder = get_geocoder(name, **kwargs)
            if geocoder.is_configured:
                providers.append(geocoder)
        except (ValueError, TypeError):
            continue

    return providers


@dataclass
class ProviderMetadata:
    """Metadata about a geocoding provider (configured or not)."""

    name: str
    service_type: str
    requires_api_key: bool
    is_configured: bool
    rate_limit_delay: float


def get_all_provider_metadata(settings: Settings) -> list[ProviderMetadata]:
    """Return metadata for all registered providers.

    For configured providers, metadata is read from the live instance.
    For unconfigured providers that can be instantiated without API keys
    (e.g., Census, Nominatim, Photon), metadata is read from a default
    instance. Providers that require mandatory constructor args fall back
    to conservative defaults.

    Args:
        settings: Application settings.

    Returns:
        List of ProviderMetadata for every registered provider.
    """
    configured = get_configured_providers(settings)
    configured_map = {p.provider_name: p for p in configured}

    metadata: list[ProviderMetadata] = []
    for name in get_available_providers():
        provider = configured_map.get(name)

        if provider is None:
            # Not configured — try to instantiate with defaults for metadata
            with contextlib.suppress(ValueError, TypeError):
                provider = get_geocoder(name)

        if provider:
            metadata.append(
                ProviderMetadata(
                    name=provider.provider_name,
                    service_type=provider.service_type.value,
                    requires_api_key=provider.requires_api_key,
                    is_configured=name in configured_map,
                    rate_limit_delay=provider.rate_limit_delay,
                )
            )
        else:
            # Provider requires mandatory args — use conservative defaults
            metadata.append(
                ProviderMetadata(
                    name=name,
                    service_type="individual",
                    requires_api_key=True,
                    is_configured=False,
                    rate_limit_delay=0.0,
                )
            )

    return metadata


__all__ = [
    "AddressComponents",
    "BaseGeocoder",
    "QUALITY_RANK",
    "BaseSuggestionSource",
    "CensusGeocoder",
    "GeocodioGeocoder",
    "GeocodeQuality",
    "GeocodeServiceType",
    "GeocodingProviderError",
    "GeocodingResult",
    "GoogleMapsGeocoder",
    "MapboxGeocoder",
    "NominatimGeocoder",
    "PhotonGeocoder",
    "ProviderMetadata",
    "cache_lookup",
    "cache_store",
    "get_all_provider_metadata",
    "get_available_providers",
    "get_configured_providers",
    "get_geocoder",
    "meters_to_degrees",
    "normalize_freeform_address",
    "parse_address_components",
    "reconstruct_address",
    "validate_address_components",
    "validate_georgia_coordinates",
]
