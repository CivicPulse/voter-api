"""Boundary comparator — compares registered vs spatially-determined boundaries.

Extracts a voter's registered district values, compares against
spatially-determined values per boundary type, and classifies
the overall match status.
"""

import contextlib
from dataclasses import dataclass, field

from voter_api.models.voter import Voter

# Mapping from boundary_type values in boundaries table to voter model fields
BOUNDARY_TYPE_TO_VOTER_FIELD: dict[str, str] = {
    "congressional": "congressional_district",
    "state_senate": "state_senate_district",
    "state_house": "state_house_district",
    "county_precinct": "county_precinct",
    "municipal_precinct": "municipal_precinct",
    "judicial": "judicial_district",
    "county_commission": "county_commission_district",
    "school_board": "school_board_district",
    "city_council": "city_council_district",
    "municipal_school_board": "municipal_school_board_district",
    "water_board": "water_board_district",
    "super_council": "super_council_district",
    "super_commissioner": "super_commissioner_district",
    "super_school_board": "super_school_board_district",
    "fire_district": "fire_district",
}

# Boundary types that are "district" vs "precinct" for classification
DISTRICT_TYPES = {
    "congressional",
    "state_senate",
    "state_house",
    "judicial",
    "county_commission",
    "school_board",
    "city_council",
    "municipal_school_board",
    "water_board",
    "super_council",
    "super_commissioner",
    "super_school_board",
    "fire_district",
}

PRECINCT_TYPES = {
    "county_precinct",
    "municipal_precinct",
}

# District types whose identifiers are purely numeric (allow zero-padding normalization)
NUMERIC_DISTRICT_TYPES = {
    "congressional",
    "state_senate",
    "state_house",
    "judicial",
    "county_commission",
    "school_board",
    "city_council",
    "municipal_school_board",
    "water_board",
    "super_council",
    "super_commissioner",
    "super_school_board",
    "fire_district",
}


def normalize_for_comparison(boundary_type: str, determined: str, registered: str) -> tuple[str, str]:
    """Normalize identifier formats so boundary and voter values are comparable.

    Handles two known format mismatches between boundary GEOIDs and GA SoS voter data:
    1. Zero-padding: boundaries store "008", voters store "8" — strip leading zeros.
    2. County FIPS prefix on precincts: boundary GEOIDs include a 3-digit county code
       prefix ("021HO3"), voters store just the precinct ("HO3") — strip prefix only
       when the suffix matches the registered value.

    Args:
        boundary_type: The boundary type being compared.
        determined: The spatially-determined identifier value.
        registered: The voter's registered identifier value.

    Returns:
        Tuple of (normalized_determined, normalized_registered).
    """
    det = determined.strip()
    reg = registered.strip()

    # For numeric district types, normalize by stripping leading zeros
    if boundary_type in NUMERIC_DISTRICT_TYPES:
        with contextlib.suppress(ValueError):
            det = str(int(det))
        with contextlib.suppress(ValueError):
            reg = str(int(reg))
        return det, reg

    # For precinct types, strip 3-digit county FIPS prefix from determined value
    # if the suffix matches the registered value
    if boundary_type in PRECINCT_TYPES and len(det) > 3:
        suffix = det[3:]
        if suffix == reg:
            return suffix, reg

    return det, reg


@dataclass
class ComparisonResult:
    """Result of comparing a voter's registered vs determined boundaries."""

    match_status: str
    determined_boundaries: dict[str, str]
    registered_boundaries: dict[str, str]
    mismatch_details: list[dict[str, str]] = field(default_factory=list)


def extract_registered_boundaries(voter: Voter) -> dict[str, str]:
    """Extract a voter's registered boundary values as a dict.

    Args:
        voter: The voter model instance.

    Returns:
        Dict mapping boundary_type to registered value (only non-null values).
    """
    registered: dict[str, str] = {}
    for boundary_type, voter_field in BOUNDARY_TYPE_TO_VOTER_FIELD.items():
        value = getattr(voter, voter_field, None)
        if value is not None and str(value).strip():
            registered[boundary_type] = str(value).strip()
    return registered


def compare_boundaries(
    determined: dict[str, str],
    registered: dict[str, str],
) -> ComparisonResult:
    """Compare determined vs registered boundaries and classify match status.

    Args:
        determined: Spatially-determined boundary assignments.
        registered: Voter's registered boundary assignments.

    Returns:
        ComparisonResult with match_status and mismatch_details.
    """
    if not determined:
        return ComparisonResult(
            match_status="unable-to-analyze",
            determined_boundaries=determined,
            registered_boundaries=registered,
        )

    mismatches: list[dict[str, str]] = []
    has_district_mismatch = False
    has_precinct_mismatch = False

    # Compare each boundary type that exists in both determined and registered
    comparable_types = set(determined.keys()) & set(registered.keys())

    for boundary_type in sorted(comparable_types):
        det_value = determined[boundary_type]
        reg_value = registered[boundary_type]

        norm_det, norm_reg = normalize_for_comparison(boundary_type, det_value, reg_value)
        if norm_det != norm_reg:
            mismatches.append(
                {
                    "boundary_type": boundary_type,
                    "registered": reg_value,
                    "determined": det_value,
                }
            )
            if boundary_type in DISTRICT_TYPES:
                has_district_mismatch = True
            if boundary_type in PRECINCT_TYPES:
                has_precinct_mismatch = True

    if not mismatches:
        match_status = "match"
    elif has_district_mismatch and has_precinct_mismatch:
        match_status = "mismatch-both"
    elif has_precinct_mismatch:
        match_status = "mismatch-precinct"
    elif has_district_mismatch:
        match_status = "mismatch-district"
    else:
        match_status = "mismatch-district"

    return ComparisonResult(
        match_status=match_status,
        determined_boundaries=determined,
        registered_boundaries=registered,
        mismatch_details=mismatches,
    )
