"""Address verification — component validation and suggestion source abstraction.

Validates parsed address components for completeness and correctness,
and defines the pluggable suggestion source interface.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from voter_api.lib.geocoder.address import AddressComponents

# Required components for a well-formed address
_REQUIRED_COMPONENTS = ["street_number", "street_name", "city", "state", "zip"]

# ZIP code pattern: 5 digits or 5+4
_ZIP_PATTERN = re.compile(r"^\d{5}(-\d{4})?$")


@dataclass
class MalformedInfo:
    """A component that is present but improperly formatted."""

    component: str
    issue: str


@dataclass
class ValidationFeedback:
    """Result of address component validation."""

    present_components: list[str] = field(default_factory=list)
    missing_components: list[str] = field(default_factory=list)
    malformed_components: list[MalformedInfo] = field(default_factory=list)
    is_well_formed: bool = False


def validate_address_components(components: AddressComponents) -> ValidationFeedback:
    """Validate parsed address components for completeness and format.

    Checks required fields (street_number, street_name, city, state, zip)
    and validates ZIP format (5-digit or ZIP+4).

    Args:
        components: Parsed address components.

    Returns:
        ValidationFeedback with present, missing, and malformed component lists.
    """
    feedback = ValidationFeedback()

    # Check each possible component
    component_map = {
        "street_number": components.street_number,
        "street_name": components.street_name,
        "street_type": components.street_type,
        "pre_direction": components.pre_direction,
        "post_direction": components.post_direction,
        "unit": components.apt_unit,
        "city": components.city,
        "state": components.state,
        "zip": components.zipcode,
    }

    for name, value in component_map.items():
        if value and value.strip():
            feedback.present_components.append(name)

    # Check required components
    for required in _REQUIRED_COMPONENTS:
        if required not in feedback.present_components:
            feedback.missing_components.append(required)

    # Validate ZIP format if present
    if "zip" in feedback.present_components and components.zipcode and not _ZIP_PATTERN.match(components.zipcode):
        feedback.malformed_components.append(
            MalformedInfo(component="zip", issue="ZIP code must be 5 digits or ZIP+4 format")
        )

    feedback.is_well_formed = len(feedback.missing_components) == 0 and len(feedback.malformed_components) == 0

    return feedback


class BaseSuggestionSource(ABC):
    """Abstract interface for pluggable address suggestion providers.

    Extension point for adding new suggestion backends (e.g., external APIs,
    USPS database). Concrete implementation: ``CacheSuggestionSource`` in
    ``voter_api.services.address_service``.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list:
        """Search for address suggestions matching the query.

        Args:
            query: Normalized address prefix.
            limit: Maximum results to return.

        Returns:
            List of suggestion objects.
        """
