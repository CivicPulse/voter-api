"""Address reconstruction and USPS Publication 28 normalization.

Reconstructs full addresses from voter address components and normalizes
them per USPS standards for geocoding input and cache keying.
"""

import re

# USPS Pub 28 directional abbreviations
DIRECTIONAL_MAP: dict[str, str] = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

# USPS Pub 28 Appendix C — common street type abbreviations
STREET_TYPE_MAP: dict[str, str] = {
    "ALLEY": "ALY",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "CIRCLE": "CIR",
    "COURT": "CT",
    "DRIVE": "DR",
    "EXPRESSWAY": "EXPY",
    "FREEWAY": "FWY",
    "HIGHWAY": "HWY",
    "LANE": "LN",
    "LOOP": "LOOP",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "ROAD": "RD",
    "SQUARE": "SQ",
    "STREET": "ST",
    "TERRACE": "TER",
    "TRAIL": "TRL",
    "TURNPIKE": "TPKE",
    "WAY": "WAY",
}

# Reverse map to detect already-abbreviated forms
_ABBREV_TO_ABBREV = {v: v for v in STREET_TYPE_MAP.values()}


def normalize_directional(direction: str) -> str:
    """Normalize a directional string to its USPS abbreviation.

    Args:
        direction: Directional text (e.g., "NORTH", "N", "NE").

    Returns:
        Abbreviated directional or the original if already abbreviated.
    """
    upper = direction.strip().upper()
    return DIRECTIONAL_MAP.get(upper, upper)


def normalize_street_type(street_type: str) -> str:
    """Normalize a street type to its USPS abbreviation.

    Args:
        street_type: Street type text (e.g., "STREET", "ST", "AVENUE").

    Returns:
        Abbreviated street type or the original if already abbreviated.
    """
    upper = street_type.strip().upper()
    return STREET_TYPE_MAP.get(upper, _ABBREV_TO_ABBREV.get(upper, upper))


def reconstruct_address(
    *,
    street_number: str | None = None,
    pre_direction: str | None = None,
    street_name: str | None = None,
    street_type: str | None = None,
    post_direction: str | None = None,
    apt_unit: str | None = None,
    city: str | None = None,
    zipcode: str | None = None,
    state: str = "GA",
) -> str:
    """Reconstruct a full address from decomposed voter address components.

    Applies USPS Publication 28 normalization:
    - Uppercase all text
    - Abbreviate directionals (NORTH → N)
    - Abbreviate street types (STREET → ST)
    - Strip leading zeros from house numbers
    - Collapse whitespace

    Args:
        street_number: House/building number.
        pre_direction: Pre-directional (e.g., N, NORTH).
        street_name: Street name.
        street_type: Street suffix (e.g., ST, STREET).
        post_direction: Post-directional (e.g., NW).
        apt_unit: Apartment/unit designator.
        city: City name.
        zipcode: ZIP code.
        state: State abbreviation (default GA).

    Returns:
        Normalized address string. Returns empty string if no street name.
    """
    if not street_name or not street_name.strip():
        return ""

    # Build street line parts
    parts: list[str] = []

    # House number — strip leading zeros
    if street_number and street_number.strip():
        parts.append(street_number.strip().lstrip("0") or "0")

    # Pre-direction
    if pre_direction and pre_direction.strip():
        parts.append(normalize_directional(pre_direction))

    # Street name (uppercase)
    parts.append(street_name.strip().upper())

    # Street type
    if street_type and street_type.strip():
        parts.append(normalize_street_type(street_type))

    # Post-direction
    if post_direction and post_direction.strip():
        parts.append(normalize_directional(post_direction))

    street_line = " ".join(parts)

    # Apt/unit
    if apt_unit and apt_unit.strip():
        apt = apt_unit.strip().upper()
        # Ensure APT/STE/UNIT prefix if not already present
        if not re.match(r"^(APT|STE|SUITE|UNIT|#)\s*", apt, re.IGNORECASE):
            apt = f"APT {apt}"
        street_line = f"{street_line} {apt}"

    # Build full address with city, state, zip
    address_parts = [street_line]
    if city and city.strip():
        address_parts.append(city.strip().upper())
    address_parts.append(state.upper())
    if zipcode and zipcode.strip():
        address_parts[-1] = f"{address_parts[-1]} {zipcode.strip()}"

    result = ", ".join(address_parts)

    # Collapse multiple spaces
    return re.sub(r"\s+", " ", result).strip()
