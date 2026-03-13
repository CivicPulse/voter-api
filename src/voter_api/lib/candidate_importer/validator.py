"""Validation for candidate import records.

Provides field-level validation for candidate records before database import.
"""

import re
from datetime import date

_ALLOWED_FILING_STATUSES = frozenset(
    {
        "qualified",
        "withdrawn",
        "disqualified",
        "deceased",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_candidate_record(record: dict) -> list[str]:
    """Validate a candidate import record and return any errors.

    Checks required fields, date formats, enum constraints, and basic
    email format.

    Args:
        record: Dictionary of candidate record fields.

    Returns:
        List of validation error strings. Empty if the record is valid.
    """
    errors: list[str] = []

    # Required: election_name
    election_name = record.get("election_name")
    if not election_name or not isinstance(election_name, str) or not election_name.strip():
        errors.append("election_name is required and must be a non-empty string")

    # Required: election_date (valid ISO date)
    election_date = record.get("election_date")
    if not election_date:
        errors.append("election_date is required")
    elif isinstance(election_date, str):
        try:
            date.fromisoformat(election_date)
        except ValueError:
            errors.append(f"election_date is not a valid ISO date: {election_date}")
    elif not isinstance(election_date, date):
        errors.append(f"election_date must be a string or date, got {type(election_date).__name__}")

    # Required: candidate_name
    candidate_name = record.get("candidate_name")
    if not candidate_name or not isinstance(candidate_name, str) or not candidate_name.strip():
        errors.append("candidate_name is required and must be a non-empty string")

    # Optional: filing_status — normalize subtypes (e.g. "qualified - signatures accepted" → "qualified")
    filing_status = record.get("filing_status")
    if filing_status is not None and filing_status != "" and not isinstance(filing_status, str):
        errors.append(f"filing_status must be a string, got {type(filing_status).__name__}")
    elif isinstance(filing_status, str) and filing_status != "" and filing_status not in _ALLOWED_FILING_STATUSES:
        # Check if it's a subtype of an allowed status (e.g. "qualified - ...")
        normalized = filing_status.split(" - ")[0].strip().lower()
        if normalized in _ALLOWED_FILING_STATUSES:
            record["filing_status"] = normalized
        else:
            errors.append(f"filing_status '{filing_status}' is not valid; allowed: {sorted(_ALLOWED_FILING_STATUSES)}")

    # Optional: email (basic format check if present)
    email = record.get("email")
    if email is not None and email != "" and not isinstance(email, str):
        errors.append(f"email must be a string, got {type(email).__name__}")
    elif isinstance(email, str) and email != "" and not _EMAIL_RE.match(email):
        errors.append(f"email '{email}' is not valid (must contain @)")

    return errors
