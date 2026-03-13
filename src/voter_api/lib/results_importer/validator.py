"""Pre-import validation for SoS results files.

Checks structural requirements before attempting database import.
"""

from voter_api.lib.election_tracker.parser import SoSFeed


def validate_results_file(feed: SoSFeed) -> list[str]:
    """Validate a parsed SoS feed for import readiness.

    Checks:
    - Has electionDate
    - Has at least one ballot item
    - Each ballot item has at least one ballot option

    Args:
        feed: Parsed SoS feed to validate.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    if not feed.electionDate or not feed.electionDate.strip():
        errors.append("Missing electionDate")

    if not feed.results.ballotItems:
        errors.append("No ballot items found in results")
    else:
        for item in feed.results.ballotItems:
            if not item.ballotOptions:
                errors.append(f"Ballot item '{item.name}' (id={item.id}) has no ballot options")

    return errors
