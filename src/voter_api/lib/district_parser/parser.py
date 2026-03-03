"""Pure-function parsing of election district text into structured components.

Parses free-text district strings from GA SoS election data (e.g.,
"State Senate - District 18") into typed components for boundary lookup
and voter district matching.
"""

import re
from dataclasses import dataclass

# Mapping from parsed district_type to the voter table column name.
# PSC is omitted because no voter column exists for PSC districts.
DISTRICT_TYPE_TO_VOTER_COLUMN: dict[str, str] = {
    "state_senate": "state_senate_district",
    "state_house": "state_house_district",
    "congressional": "congressional_district",
    "county_commission": "county_commission_district",
}

# Mapping from parsed district_type to the boundary_type value in the
# boundaries table. These happen to be identical, but explicit is better.
DISTRICT_TYPE_TO_BOUNDARY_TYPE: dict[str, str] = {
    "state_senate": "state_senate",
    "state_house": "state_house",
    "congressional": "congressional",
    "psc": "psc",
    "county_commission": "county_commission",
}

# Ordered list of (prefix, district_type) for matching.
# Longer prefixes first to avoid partial matches.
_PREFIX_MAP: list[tuple[str, str]] = [
    ("state house of representatives", "state_house"),
    ("us house of representatives", "congressional"),
    ("state senate", "state_senate"),
    ("psc", "psc"),
]

_DISTRICT_NUMBER_RE = re.compile(r"District\s+(\d+)", re.IGNORECASE)
_PARTY_SUFFIX_RE = re.compile(r"-\s*(Dem|Rep)\s*$", re.IGNORECASE)
_COUNTY_COMMISSION_RE = re.compile(r"^(.+?)\s+County\s+Commission", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedDistrict:
    """Structured result of parsing an election district string.

    Attributes:
        district_type: Normalized type (e.g. "state_senate", "congressional").
        district_identifier: Unpadded district number as extracted (e.g. "18").
        party: Party suffix for PSC primaries (e.g. "Dem", "Rep").
        county: County name for county_commission districts (e.g. "Bibb").
        raw: The original unparsed district string.
    """

    district_type: str | None
    district_identifier: str | None
    party: str | None
    county: str | None
    raw: str


def parse_election_district(district: str) -> ParsedDistrict:
    """Parse an election district text into structured components.

    Handles observed GA SoS patterns including:
    - "State Senate - District 18"
    - "State Senate District 18" (no dash)
    - "State House of Representatives - District 94"
    - "US House of Representatives - District 14"
    - "PSC - District 3"
    - "PSC - District 3 - Dem" (party suffix)
    - "Special State Senate - District 21" (special prefix)
    - "Bibb County Commission District 5" (county commission)
    - ".../ Para la Cámara..." (Spanish translation suffix)

    Args:
        district: Raw district text from election record.

    Returns:
        ParsedDistrict with extracted components, or all-None fields
        if the format is unrecognized.
    """
    raw = district

    # 1. Strip Spanish translations (split on "/", take first part)
    if "/" in district:
        district = district.split("/", 1)[0].strip()

    # 2. Strip "Special " prefix (case-insensitive)
    if district.lower().startswith("special "):
        district = district[len("special ") :]

    # 3. Match known prefix -> district_type
    district_type: str | None = None
    lower = district.lower()
    for prefix, dtype in _PREFIX_MAP:
        if lower.startswith(prefix):
            district_type = dtype
            break

    # 3b. Try county commission pattern: "<County> County Commission District <N>"
    county: str | None = None
    if district_type is None:
        cc_match = _COUNTY_COMMISSION_RE.match(district)
        if cc_match:
            district_type = "county_commission"
            county = cc_match.group(1)

    if district_type is None:
        return ParsedDistrict(
            district_type=None,
            district_identifier=None,
            party=None,
            county=None,
            raw=raw,
        )

    # 4. Extract party suffix before district number (e.g. "- Dem")
    party: str | None = None
    party_match = _PARTY_SUFFIX_RE.search(district)
    if party_match:
        party = party_match.group(1)

    # 5. Extract district number
    district_identifier: str | None = None
    number_match = _DISTRICT_NUMBER_RE.search(district)
    if number_match:
        district_identifier = number_match.group(1)

    return ParsedDistrict(
        district_type=district_type,
        district_identifier=district_identifier,
        party=party,
        county=county,
        raw=raw,
    )


def pad_district_identifier(identifier: str, width: int = 3) -> str:
    """Zero-pad a district identifier to match boundary_identifier format.

    Boundary identifiers in the boundaries table are zero-padded to 3 digits
    (e.g. "018"), while election and voter data use unpadded numbers ("18").

    Args:
        identifier: Unpadded district identifier (e.g. "18", "3", "130").
        width: Target width for zero-padding (default 3).

    Returns:
        Zero-padded identifier string.
    """
    return identifier.zfill(width)
