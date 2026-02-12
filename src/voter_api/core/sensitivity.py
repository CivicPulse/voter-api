"""Data sensitivity tier classification system.

Defines sensitivity tiers for field-level access control per FR-022.
Government-sourced fields come directly from the SoS voter file.
System-generated fields are produced by the application (validated addresses,
manual geocoding coordinates, analysis results).
"""

import enum
from typing import Any


class SensitivityTier(enum.StrEnum):
    """Data sensitivity classification tiers."""

    GOVERNMENT_SOURCED = "government_sourced"
    SYSTEM_GENERATED = "system_generated"


def sensitivity_tier(tier: SensitivityTier) -> Any:
    """Field metadata marker for sensitivity tier classification.

    Use as Pydantic Field json_schema_extra or in field metadata to tag
    response schema fields by their data sensitivity tier.

    Args:
        tier: The sensitivity tier for the field.

    Returns:
        A dict suitable for use as Pydantic Field metadata.
    """
    return {"sensitivity_tier": tier.value}
