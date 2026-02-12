"""Boundary comparator — compares registered vs spatially-determined boundaries.

Extracts a voter's registered district values, compares against
spatially-determined values per boundary type, and classifies
the overall match status.
"""

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
    "fire": "fire_district",
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
    "fire",
}

PRECINCT_TYPES = {
    "county_precinct",
    "municipal_precinct",
}


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

        if det_value != reg_value:
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
