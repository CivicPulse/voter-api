"""Shared normalization utilities for voter data fields."""


def normalize_registration_number(value: str) -> str:
    """Strip leading zeros from a voter registration number.

    GA SoS voter history CSVs zero-pad registration numbers (e.g., "00013148")
    while the voter file does not. This function normalizes to the unpadded
    format so joins between the two datasets work correctly.

    Note:
        Empty strings return ``"0"`` (same as all-zeros input). Callers
        should guard with ``None`` checks for absent data before invoking
        this function — the CSV parser handles this by normalizing only
        non-empty values.

    Args:
        value: Raw registration number string (must not be empty — see note).

    Returns:
        Registration number with leading zeros removed. Returns "0" for
        all-zeros input to avoid an empty string.
    """
    return value.lstrip("0") or "0"
