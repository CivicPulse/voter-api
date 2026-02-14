"""Address reconstruction, freeform normalization, and component parsing.

Reconstructs full addresses from voter address components, normalizes freeform
address strings per USPS Publication 28 standards, and parses freeform strings
into structured address components.
"""

import re
from dataclasses import dataclass

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


# --- Build word-boundary regex patterns for freeform normalization ---

# All known abbreviation values (to avoid re-abbreviating)
_KNOWN_ABBREVS = set(STREET_TYPE_MAP.values()) | set(DIRECTIONAL_MAP.values())

# Build combined mapping: full word -> abbreviation (for both street types and directionals)
_FREEFORM_REPLACEMENTS: dict[str, str] = {}
_FREEFORM_REPLACEMENTS.update(STREET_TYPE_MAP)
_FREEFORM_REPLACEMENTS.update(DIRECTIONAL_MAP)

# Pre-compile word-boundary patterns for each full word (longest first to avoid partial matches)
_FREEFORM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\b{re.escape(word)}\b"), abbrev)
    for word, abbrev in sorted(_FREEFORM_REPLACEMENTS.items(), key=lambda x: -len(x[0]))
]


def normalize_freeform_address(address: str) -> str:
    """Normalize a freeform address string per USPS Publication 28.

    Applies: uppercase, trim, collapse whitespace, USPS abbreviations
    for street types and directionals using word-boundary matching.

    Args:
        address: Raw freeform address string.

    Returns:
        Normalized address string suitable for cache keying.
    """
    if not address or not address.strip():
        return ""

    result = address.strip().upper()
    result = re.sub(r"\s+", " ", result)

    for pattern, replacement in _FREEFORM_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


@dataclass
class AddressComponents:
    """Parsed address components from a freeform address string."""

    street_number: str | None = None
    pre_direction: str | None = None
    street_name: str | None = None
    street_type: str | None = None
    post_direction: str | None = None
    apt_unit: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert to a dict with keys matching the Address model columns.

        Returns:
            Dictionary of component name to value.
        """
        return {
            "street_number": self.street_number,
            "pre_direction": self.pre_direction,
            "street_name": self.street_name,
            "street_type": self.street_type,
            "post_direction": self.post_direction,
            "apt_unit": self.apt_unit,
            "city": self.city,
            "state": self.state,
            "zipcode": self.zipcode,
        }


# All known abbreviated street types (values from STREET_TYPE_MAP) for detection
_ALL_STREET_TYPES = set(STREET_TYPE_MAP.values()) | set(STREET_TYPE_MAP.keys())

# All known abbreviated directionals for detection
_ALL_DIRECTIONALS = set(DIRECTIONAL_MAP.values()) | set(DIRECTIONAL_MAP.keys())

# ZIP code pattern: 5 digits or 5+4
_ZIP_PATTERN = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")

# Leading digits for street number
_STREET_NUMBER_PATTERN = re.compile(r"^(\d+[A-Z]?)\b")

# US state abbreviations (2-letter)
_STATE_ABBREVS = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}

# Unit/apartment indicators
_UNIT_INDICATORS = {"APT", "STE", "SUITE", "UNIT", "#", "BLDG", "FL", "RM", "DEPT"}


def parse_address_components(address: str) -> AddressComponents:
    """Parse a freeform address string into structured components.

    Splits on commas to separate street line / city / state+zip, then
    extracts individual components from the street line. Best-effort
    parsing — not all components may be extracted from ambiguous input.

    Args:
        address: Freeform address string.

    Returns:
        AddressComponents with extracted fields.
    """
    if not address or not address.strip():
        return AddressComponents()

    normalized = address.strip().upper()
    parts = [p.strip() for p in normalized.split(",") if p.strip()]

    components = AddressComponents()

    if not parts:
        return components

    # Extract from the last part(s): state and zip
    # Try to find ZIP in the entire string
    zip_match = _ZIP_PATTERN.search(normalized)
    if zip_match:
        components.zipcode = zip_match.group(1)

    # Try to extract state from the last or second-to-last part
    if len(parts) >= 2:
        last_part = parts[-1]
        last_tokens = last_part.split()

        # Check if last part contains state + zip or just state
        for token in last_tokens:
            clean = token.strip()
            if clean in _STATE_ABBREVS:
                components.state = clean
                break

        # If no state found in last part, check second-to-last
        if components.state is None and len(parts) >= 3:
            second_last_tokens = parts[-2].split()
            for token in second_last_tokens:
                clean = token.strip()
                if clean in _STATE_ABBREVS:
                    components.state = clean
                    break

    # Extract city: typically the part before state/zip
    if len(parts) >= 3:
        # parts[0] = street, parts[1] = city, parts[2] = state+zip
        components.city = parts[1].strip()
    elif len(parts) == 2:
        # Could be "street, city" or "street, state zip"
        second = parts[1].strip()
        second_tokens = second.split()
        # If second part has a state abbreviation, it's likely "state zip" not city
        has_state = any(t in _STATE_ABBREVS for t in second_tokens)
        if has_state and components.state:
            # "street, state zip" — no city
            pass
        else:
            # "street, city" — the second part is the city
            # But remove any state/zip from it
            city_tokens = [t for t in second_tokens if t not in _STATE_ABBREVS and not _ZIP_PATTERN.match(t)]
            if city_tokens:
                components.city = " ".join(city_tokens)

    # Parse the street line (first part)
    street_line = parts[0]
    tokens = street_line.split()

    if not tokens:
        return components

    idx = 0

    # Extract street number (leading digits)
    num_match = _STREET_NUMBER_PATTERN.match(tokens[0])
    if num_match:
        components.street_number = num_match.group(1)
        idx = 1

    if idx >= len(tokens):
        return components

    # Check for pre-directional
    if tokens[idx].upper() in _ALL_DIRECTIONALS and idx + 1 < len(tokens):
        components.pre_direction = normalize_directional(tokens[idx])
        idx += 1

    # Find unit indicator and split
    unit_start = None
    for i in range(idx, len(tokens)):
        if tokens[i] in _UNIT_INDICATORS:
            unit_start = i
            break

    if unit_start is not None:
        street_tokens = tokens[idx:unit_start]
        components.apt_unit = " ".join(tokens[unit_start:])
    else:
        street_tokens = tokens[idx:]

    if not street_tokens:
        return components

    # Extract post-directional (last token if it's a directional)
    if len(street_tokens) > 1 and street_tokens[-1] in _ALL_DIRECTIONALS:
        components.post_direction = normalize_directional(street_tokens[-1])
        street_tokens = street_tokens[:-1]

    # Extract street type (last remaining token if it's a known type)
    if len(street_tokens) > 1:
        last_upper = street_tokens[-1].upper()
        if last_upper in _ALL_STREET_TYPES:
            components.street_type = normalize_street_type(street_tokens[-1])
            street_tokens = street_tokens[:-1]

    # Remaining tokens form the street name
    if street_tokens:
        components.street_name = " ".join(street_tokens)

    return components
