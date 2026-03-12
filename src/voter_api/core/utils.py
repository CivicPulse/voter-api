"""Core utility functions shared across services."""


def _mask_vrn(vrn: str) -> str:
    """Mask a voter registration number for safe inclusion in logs.

    Returns the last 4 characters prefixed with '***' to prevent
    exposing full registration numbers in error logs.

    Args:
        vrn: Voter registration number string.

    Returns:
        Masked string, e.g. ``"***1234"``.
    """
    return f"***{vrn[-4:]}"
