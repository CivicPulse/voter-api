"""Import diff generation — compare current import against existing records.

Identifies added, removed (soft-deleted), and updated voter records.
"""

from typing import Any


def generate_diff(
    current_reg_numbers: set[str],
    previous_reg_numbers: set[str],
    updated_reg_numbers: set[str] | None = None,
) -> dict[str, list[str]]:
    """Generate a diff between current and previous import registration numbers.

    Args:
        current_reg_numbers: Registration numbers in the current import.
        previous_reg_numbers: Registration numbers from the previous import.
        updated_reg_numbers: Registration numbers that were updated (optional).

    Returns:
        Dictionary with 'added', 'removed', and 'updated' registration number lists.
    """
    added = current_reg_numbers - previous_reg_numbers
    removed = previous_reg_numbers - current_reg_numbers
    updated = updated_reg_numbers or set()

    return {
        "added": sorted(added),
        "removed": sorted(removed),
        "updated": sorted(updated),
    }


def detect_field_changes(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    compare_fields: list[str] | None = None,
) -> dict[str, tuple[Any, Any]]:
    """Detect field-level changes between existing and incoming records.

    Args:
        existing: The current database record as a dict.
        incoming: The incoming import record as a dict.
        compare_fields: Fields to compare (None = all shared keys).

    Returns:
        Dictionary of field_name → (old_value, new_value) for changed fields.
    """
    if compare_fields is None:
        compare_fields = [k for k in incoming if k in existing and not k.startswith("_")]

    changes = {}
    for field in compare_fields:
        old_val = existing.get(field)
        new_val = incoming.get(field)
        if old_val != new_val:
            changes[field] = (old_val, new_val)

    return changes
