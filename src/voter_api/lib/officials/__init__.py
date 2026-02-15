"""Officials library — pluggable elected-official data sourcing.

Public API:
    - OfficialRecord: Normalized dataclass for official data from any provider
    - BaseOfficialsProvider: Abstract provider interface
    - OfficialsProviderError: Provider-level error
    - get_provider: Provider factory/registry
"""

from typing import Any

from loguru import logger

from voter_api.lib.officials.base import BaseOfficialsProvider, OfficialRecord, OfficialsProviderError
from voter_api.lib.officials.congress_gov import CongressGovProvider
from voter_api.lib.officials.open_states import OpenStatesProvider

# Provider registry — populated as concrete providers are implemented
_PROVIDERS: dict[str, type[BaseOfficialsProvider]] = {}


def get_provider(name: str, **kwargs: Any) -> BaseOfficialsProvider:
    """Get an officials-provider instance by name.

    Args:
        name: Provider name (e.g., "open_states", "congress_gov").
        **kwargs: Additional arguments forwarded to the provider constructor.

    Returns:
        An instance of the requested provider.

    Raises:
        ValueError: If the provider is not registered.
    """
    cls = _PROVIDERS.get(name)
    if cls is None:
        msg = f"Unknown officials provider: {name!r}. Available: {list(_PROVIDERS.keys())}"
        raise ValueError(msg)
    return cls(**kwargs)


def register_provider(name: str, cls: type[BaseOfficialsProvider]) -> None:
    """Register a provider class in the global registry.

    Args:
        name: Short name for the provider.
        cls: Provider class (must subclass BaseOfficialsProvider).
    """
    if name in _PROVIDERS:
        logger.warning(f"Overwriting existing officials provider {name!r}")
    _PROVIDERS[name] = cls


register_provider("open_states", OpenStatesProvider)
register_provider("congress_gov", CongressGovProvider)

__all__ = [
    "BaseOfficialsProvider",
    "CongressGovProvider",
    "OfficialRecord",
    "OfficialsProviderError",
    "OpenStatesProvider",
    "get_provider",
    "register_provider",
]
