"""StrEnum definitions for JSONL schema validation.

These enums are the single source of truth for controlled vocabularies
used in the JSONL data contracts. They are independent of the existing
enums in schemas/candidate.py to keep the JSONL package self-contained
and usable without the rest of the application.
"""

import enum


class ElectionType(enum.StrEnum):
    """Base election type classification.

    Categorises the kind of election independently from whether it
    progressed to a runoff or recount (see ElectionStage).
    """

    GENERAL_PRIMARY = "general_primary"
    GENERAL = "general"
    SPECIAL = "special"
    SPECIAL_PRIMARY = "special_primary"
    MUNICIPAL = "municipal"


class ElectionStage(enum.StrEnum):
    """Resolution mechanism for an election contest.

    Separates the phase of the electoral process from the base election
    type so that a contest can be, e.g., a ``general_primary`` at the
    ``runoff`` stage.
    """

    ELECTION = "election"
    RUNOFF = "runoff"
    RECOUNT = "recount"


class FilingStatus(enum.StrEnum):
    """Candidate filing status lifecycle.

    Tracks whether a candidate is actively qualified to appear on the
    ballot, has withdrawn, been disqualified, or is a write-in.
    """

    QUALIFIED = "qualified"
    WITHDRAWN = "withdrawn"
    DISQUALIFIED = "disqualified"
    WRITE_IN = "write_in"


class LinkType(enum.StrEnum):
    """Allowed candidate link types.

    Matches the DB constraint on candidate_links.link_type exactly.
    """

    WEBSITE = "website"
    CAMPAIGN = "campaign"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"
    OTHER = "other"


class BoundaryType(enum.StrEnum):
    """Political/administrative boundary type values.

    Mirrors ``BOUNDARY_TYPES`` in ``src/voter_api/models/boundary.py``.
    The authoritative source is the DB model list; this enum reflects
    the list at the time of Phase 1.
    """

    CONGRESSIONAL = "congressional"
    STATE_SENATE = "state_senate"
    STATE_HOUSE = "state_house"
    JUDICIAL = "judicial"
    PSC = "psc"
    COUNTY = "county"
    COUNTY_COMMISSION = "county_commission"
    SCHOOL_BOARD = "school_board"
    CITY_COUNCIL = "city_council"
    MUNICIPAL_SCHOOL_BOARD = "municipal_school_board"
    WATER_BOARD = "water_board"
    SUPER_COUNCIL = "super_council"
    SUPER_COMMISSIONER = "super_commissioner"
    SUPER_SCHOOL_BOARD = "super_school_board"
    FIRE_DISTRICT = "fire_district"
    COUNTY_PRECINCT = "county_precinct"
    MUNICIPAL_PRECINCT = "municipal_precinct"
    US_SENATE = "us_senate"
