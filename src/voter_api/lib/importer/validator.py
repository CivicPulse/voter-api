"""Voter record validation rules.

Validates required fields, format constraints, and flags address-less voters.
"""

from datetime import UTC, datetime
from typing import Any

from loguru import logger

REQUIRED_FIELDS = ["county", "voter_registration_number", "status", "last_name", "first_name"]

VALID_STATUSES = {"ACTIVE", "INACTIVE"}


def validate_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a single voter record.

    Args:
        record: Dictionary of voter field name → value.

    Returns:
        Tuple of (is_valid, list of error messages).
    """
    errors: list[str] = []

    # Required field checks
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            errors.append(f"Missing required field: {field}")

    # Birth year validation
    birth_year = record.get("birth_year")
    if birth_year is not None:
        try:
            year = int(birth_year)
            current_year = datetime.now(UTC).year
            if year < 1900 or year > current_year:
                errors.append(f"Invalid birth_year: {birth_year} (must be 1900-{current_year})")
        except (ValueError, TypeError):
            errors.append(f"Invalid birth_year format: {birth_year}")

    # Status enum check
    status = record.get("status")
    if status and status.upper() not in VALID_STATUSES:
        # Log warning but don't reject — SoS may have other statuses
        logger.warning(f"Non-standard status value: {status}")

    return len(errors) == 0, errors


def is_geocodable(record: dict[str, Any]) -> bool:
    """Check if a voter record has sufficient address data for geocoding.

    Args:
        record: Dictionary of voter field name → value.

    Returns:
        True if the record has at least a street name and city or zipcode.
    """
    has_street = bool(record.get("residence_street_name"))
    has_city_or_zip = bool(record.get("residence_city") or record.get("residence_zipcode"))
    return has_street and has_city_or_zip


def validate_batch(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate a batch of voter records.

    Args:
        records: List of voter record dictionaries.

    Returns:
        Tuple of (valid_records, failed_records with errors attached).
    """
    valid = []
    failed = []

    for record in records:
        is_valid, errors = validate_record(record)
        if is_valid:
            record["_geocodable"] = is_geocodable(record)
            valid.append(record)
        else:
            record["_validation_errors"] = errors
            failed.append(record)

    return valid, failed
