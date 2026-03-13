"""Candidate name and party parsing from SoS results ballot options.

Extracts clean candidate names, party affiliations, and incumbent status
from the raw ballot option format used in GA Secretary of State results.
"""

import re
from dataclasses import dataclass

# Matches trailing parenthetical markers like (Rep), (Dem), (I), (I) (Rep)
_PAREN_MARKER_RE = re.compile(r"\s*\((?:Rep|Dem|Ind|Lib|NP|I)\)", re.IGNORECASE)

_PARTY_MAP: dict[str, str] = {
    "rep": "Republican",
    "dem": "Democrat",
    "i": "Independent",
    "ind": "Independent",
    "lib": "Libertarian",
    "np": "Nonpartisan",
}


@dataclass(frozen=True)
class ParsedCandidate:
    """Parsed candidate information from a ballot option.

    Attributes:
        full_name: Cleaned candidate name without party markers.
        party: Full party name (e.g., "Republican"), or None.
        is_incumbent: True if the ballot option had an (I) marker.
        ballot_order: Position on ballot (1-indexed).
        sos_ballot_option_id: The SoS ballot option ID string.
        vote_count: Total votes received.
    """

    full_name: str
    party: str | None
    is_incumbent: bool
    ballot_order: int
    sos_ballot_option_id: str
    vote_count: int


def normalize_party(code: str) -> str | None:
    """Normalize a party code to its full name.

    Args:
        code: Party code from SoS feed (e.g., "Rep", "Dem", "").

    Returns:
        Full party name, or None for empty/unknown codes.
    """
    if not code or not code.strip():
        return None
    return _PARTY_MAP.get(code.strip().lower())


def parse_candidate_name(raw_name: str, political_party: str) -> ParsedCandidate:
    """Parse a candidate name from a SoS ballot option.

    Strips trailing parenthetical markers like "(Rep)", "(Dem)", "(I)".
    Detects incumbent status from "(I)" marker.
    Uses the ``politicalParty`` field as the authoritative party source.

    Args:
        raw_name: Raw ballot option name (e.g., "Tim Echols (I) (Rep)").
        political_party: The politicalParty field from the ballot option.

    Returns:
        ParsedCandidate with ballot_order=0 and sos_ballot_option_id=""
        (caller should set these from the BallotOption context).
    """
    # Detect incumbent flag before stripping
    is_incumbent = "(I)" in raw_name or "(i)" in raw_name

    # Strip all parenthetical markers
    clean_name = _PAREN_MARKER_RE.sub("", raw_name).strip()

    # Normalize party from the authoritative field
    party = normalize_party(political_party)

    return ParsedCandidate(
        full_name=clean_name,
        party=party,
        is_incumbent=is_incumbent,
        ballot_order=0,
        sos_ballot_option_id="",
        vote_count=0,
    )
