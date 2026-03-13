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
    "school_board": "school_board_district",
    "board_of_education": "school_board_district",
    "city_council": "city_council_district",
    "judicial": "judicial_district",
}

# Mapping from parsed district_type to the boundary_type value in the
# boundaries table. These happen to be identical, but explicit is better.
DISTRICT_TYPE_TO_BOUNDARY_TYPE: dict[str, str] = {
    "state_senate": "state_senate",
    "state_house": "state_house",
    "congressional": "congressional",
    "psc": "psc",
    "county_commission": "county_commission",
    "school_board": "school_board",
    "board_of_education": "school_board",
    "county_office": "county",
}

# Georgia Public Service Commission district-to-county mapping.
# PSC districts don't have a voter column — voters are resolved via county membership.
# Source: GA PSC official district map.
PSC_DISTRICT_COUNTIES: dict[str, list[str]] = {
    "1": [
        "Appling",
        "Atkinson",
        "Bacon",
        "Baker",
        "Ben Hill",
        "Berrien",
        "Brantley",
        "Brooks",
        "Bulloch",
        "Burke",
        "Calhoun",
        "Camden",
        "Candler",
        "Charlton",
        "Chatham",
        "Clinch",
        "Coffee",
        "Colquitt",
        "Cook",
        "Decatur",
        "Dodge",
        "Dougherty",
        "Early",
        "Echols",
        "Effingham",
        "Emanuel",
        "Evans",
        "Glynn",
        "Grady",
        "Irwin",
        "Jeff Davis",
        "Jefferson",
        "Jenkins",
        "Johnson",
        "Lanier",
        "Laurens",
        "Lee",
        "Liberty",
        "Long",
        "Lowndes",
        "McIntosh",
        "Miller",
        "Mitchell",
        "Montgomery",
        "Pierce",
        "Quitman",
        "Randolph",
        "Richmond",
        "Screven",
        "Seminole",
        "Tattnall",
        "Terrell",
        "Thomas",
        "Tift",
        "Toombs",
        "Treutlen",
        "Turner",
        "Ware",
        "Wayne",
        "Wheeler",
        "Wilcox",
        "Worth",
    ],
    "2": [
        "Baldwin",
        "Bibb",
        "Bleckley",
        "Bryan",
        "Butts",
        "Chattahoochee",
        "Clay",
        "Columbia",
        "Crawford",
        "Crisp",
        "Dooly",
        "Glascock",
        "Hancock",
        "Harris",
        "Houston",
        "Jasper",
        "Jones",
        "Lamar",
        "Lincoln",
        "Macon",
        "Marion",
        "McDuffie",
        "Meriwether",
        "Monroe",
        "Muscogee",
        "Peach",
        "Pike",
        "Pulaski",
        "Putnam",
        "Schley",
        "Stewart",
        "Sumter",
        "Talbot",
        "Taliaferro",
        "Taylor",
        "Telfair",
        "Twiggs",
        "Upson",
        "Warren",
        "Washington",
        "Webster",
        "Wilkes",
        "Wilkinson",
    ],
    "3": [
        "Barrow",
        "Carroll",
        "Cherokee",
        "Clarke",
        "Clayton",
        "Coweta",
        "DeKalb",
        "Douglas",
        "Elbert",
        "Fayette",
        "Greene",
        "Gwinnett",
        "Hart",
        "Heard",
        "Henry",
        "Jackson",
        "Madison",
        "Morgan",
        "Newton",
        "Oconee",
        "Oglethorpe",
        "Rockdale",
        "Spalding",
        "Troup",
        "Walton",
    ],
    "4": [
        "Banks",
        "Catoosa",
        "Chattooga",
        "Dade",
        "Dawson",
        "Fannin",
        "Floyd",
        "Franklin",
        "Gilmer",
        "Gordon",
        "Habersham",
        "Hall",
        "Haralson",
        "Lumpkin",
        "Murray",
        "Paulding",
        "Pickens",
        "Polk",
        "Rabun",
        "Stephens",
        "Towns",
        "Union",
        "Walker",
        "White",
        "Whitfield",
    ],
    "5": [
        "Bartow",
        "Cobb",
        "Forsyth",
        "Fulton",
        "North Fulton",
        "South Fulton",
    ],
}

# Build a reverse lookup: county name (uppercased) -> PSC district ID.
_COUNTY_TO_PSC_DISTRICT: dict[str, str] = {
    county.upper(): district_id for district_id, counties in PSC_DISTRICT_COUNTIES.items() for county in counties
}


def get_psc_district_for_county(county_name: str) -> str | None:
    """Return the PSC district ID for a given county name, or None if not found.

    Args:
        county_name: County name (case-insensitive, leading/trailing whitespace stripped).

    Returns:
        PSC district ID string (e.g. "1", "3") or None if no match.
    """
    normalized = county_name.strip().upper()
    return _COUNTY_TO_PSC_DISTRICT.get(normalized)


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
_COUNTY_COMMISSION_RE = re.compile(r"^([A-Za-z]+(?:\s+[A-Za-z]+)*?)\s+County\s+Commission", re.IGNORECASE)

# --- Contest name parsing (Qualified Candidates CSV) ---

_PAREN_PARTY_RE = re.compile(r"\(([A-Za-z]+)\)\s*$")
_CONTEST_DISTRICT_RE = re.compile(r"(?:District|Seat|Post|Ward|Division)\s+(\d+)", re.IGNORECASE)

_PARTY_ABBREV_MAP: dict[str, str] = {
    "R": "Republican",
    "D": "Democrat",
    "NP": "Nonpartisan",
    "L": "Libertarian",
    "I": "Independent",
}

_STATEWIDE_OFFICES: frozenset[str] = frozenset(
    {
        "governor",
        "lieutenant governor",
        "secretary of state",
        "attorney general",
        "commissioner of agriculture",
        "commissioner of insurance",
        "commissioner of labor",
        "state school superintendent",
    }
)


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


def parse_contest_name(
    text: str,
    county: str | None = None,
    municipality: str | None = None,
) -> ParsedDistrict:
    """Parse a contest name from the GA SoS Qualified Candidates CSV.

    Handles contest name patterns like "U.S House of Representatives, District 11 (R)",
    "Governor (D)", "Superior Court Judge, Blue Ridge Judicial Circuit (NP)", etc.

    Args:
        text: Raw contest name string from the Qualified Candidates CSV.
        county: County name to attach to county-level district types.
        municipality: Municipality name to attach to municipal district types.

    Returns:
        ParsedDistrict with extracted components. ``district_type`` is None
        if the contest name format is unrecognized.
    """
    raw = text

    # 1. Extract party from parenthetical suffix, e.g. "(R)"
    party: str | None = None
    party_match = _PAREN_PARTY_RE.search(text)
    if party_match:
        abbrev = party_match.group(1)
        party = _PARTY_ABBREV_MAP.get(abbrev, abbrev)
        text = text[: party_match.start()].strip()

    # 2. Extract district/seat/post/ward number
    district_identifier: str | None = None
    id_match = _CONTEST_DISTRICT_RE.search(text)
    if id_match:
        district_identifier = id_match.group(1)

    # 3. Classify district_type (check in priority order)
    lower = text.lower()

    district_type: str | None = None
    result_county: str | None = None

    if "u.s house" in lower or "u.s. house" in lower:
        district_type = "congressional"
    elif "u.s senate" in lower or "u.s. senate" in lower:
        district_type = "us_senate"
    elif lower.startswith("state senate"):
        district_type = "state_senate"
    elif lower.startswith("state house"):
        district_type = "state_house"
    elif lower.startswith("public service commission") or lower.startswith("psc"):
        district_type = "psc"
    elif _is_statewide(lower):
        district_type = "statewide"
    elif "board of education" in lower or "school board" in lower:
        district_type = "board_of_education"
        result_county = county
    elif "county commiss" in lower or "board of commissioners" in lower:
        district_type = "county_commission"
        result_county = county
    elif _is_county_office(lower):
        # Must be checked before judicial — "Clerk of Superior Court" and
        # "Probate Judge" contain judicial keywords but are county offices.
        district_type = "county_office"
        result_county = county
    elif _is_judicial(lower):
        district_type = "judicial"
    elif lower.startswith("city council"):
        district_type = "city_council"
        result_county = municipality
    elif _is_municipal(lower):
        district_type = "municipal"
        result_county = municipality

    return ParsedDistrict(
        district_type=district_type,
        district_identifier=district_identifier,
        party=party,
        county=result_county,
        raw=raw,
    )


def _is_statewide(lower: str) -> bool:
    """Check if the lowercased contest name matches a statewide office."""
    # Strip trailing commas/content after comma for matching
    name = lower.split(",")[0].strip()
    return name in _STATEWIDE_OFFICES


def _is_judicial(lower: str) -> bool:
    """Check if the lowercased contest name contains judicial keywords."""
    judicial_keywords = (
        "supreme court",
        "court of appeals",
        "superior court",
        "district attorney",
        "solicitor",
        "judge",
        "magistrate",
        "juvenile court",
    )
    return any(kw in lower for kw in judicial_keywords)


def _is_county_office(lower: str) -> bool:
    """Check if the lowercased contest name matches a county office."""
    county_offices = (
        "clerk of superior court",
        "sheriff",
        "tax commissioner",
        "coroner",
        "probate judge",
        "surveyor",
    )
    return any(lower.startswith(office) for office in county_offices)


def _is_municipal(lower: str) -> bool:
    """Check if the lowercased contest name matches a municipal office."""
    municipal_keywords = ("mayor", "city council", "council member", "alderman")
    return any(lower.startswith(kw) for kw in municipal_keywords)


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
