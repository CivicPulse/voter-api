"""Individual normalization rule functions for election data fields.

Each function is a pure, stateless transformation with no file I/O or
database access. All functions are idempotent: applying them twice
produces the same result as applying them once.
"""

from __future__ import annotations

from voter_api.lib.normalizer.title_case import smart_title_case

# Placeholder values that should pass through unchanged
_PLACEHOLDERS: frozenset[str] = frozenset({"--", "\u2014", "-"})


def normalize_url(url: str) -> str:
    """Normalize a URL to lowercase https:// form.

    Handles the following cases:
    - Missing protocol (www.example.com -> https://www.example.com)
    - Plain domain without www (example.com -> https://example.com)
    - HTTP upgraded to HTTPS
    - Already-correct HTTPS URLs (idempotent)
    - Placeholder values (-- or em-dash) passed through unchanged
    - Empty or whitespace-only strings passed through unchanged

    Args:
        url: The URL string to normalize.

    Returns:
        Normalized URL string, or the original if it is a placeholder
        or unparseable.
    """
    if not url or url.strip() == "" or url.strip() in _PLACEHOLDERS:
        return url

    stripped = url.strip()

    # Pass through placeholder values
    if stripped in _PLACEHOLDERS:
        return url

    # If it looks like a plain domain (no scheme), add https://
    lower = stripped.lower()
    if not lower.startswith("http://") and not lower.startswith("https://"):  # NOSONAR
        lower = "https://" + lower

    # Upgrade http to https
    if lower.startswith("http://"):  # NOSONAR
        lower = "https://" + lower[7:]

    return lower


def normalize_date(date_str: str, *, target_format: str = "slash") -> str:
    """Normalize a date string to a consistent format.

    Supports parsing:
    - MM/DD/YYYY or M/D/YYYY (slash format)
    - YYYY-MM-DD or YYYY-M-D (ISO format)

    Output formats:
    - "slash": MM/DD/YYYY (zero-padded, default)
    - "iso": YYYY-MM-DD (zero-padded)

    Placeholder values (-- or em-dash) and unparseable strings are
    returned unchanged.

    Args:
        date_str: The date string to normalize.
        target_format: The output format. One of "slash" or "iso".
            Defaults to "slash".

    Returns:
        Normalized date string, or the original if unparseable.
    """
    if not date_str or date_str.strip() in _PLACEHOLDERS:
        return date_str

    stripped = date_str.strip()

    # Try slash format: M/D/YYYY or MM/DD/YYYY
    if "/" in stripped:
        parts = stripped.split("/")
        if len(parts) == 3:
            month_s, day_s, year_s = parts
            try:
                month = int(month_s)
                day = int(day_s)
                year = int(year_s)
                if 1 <= month <= 12 and 1 <= day <= 31 and 1000 <= year <= 9999:
                    if target_format == "iso":
                        return f"{year:04d}-{month:02d}-{day:02d}"
                    return f"{month:02d}/{day:02d}/{year:04d}"
            except ValueError:
                pass

    # Try ISO format: YYYY-MM-DD or YYYY-M-D
    if "-" in stripped:
        parts = stripped.split("-")
        if len(parts) == 3:
            year_s, month_s, day_s = parts
            try:
                year = int(year_s)
                month = int(month_s)
                day = int(day_s)
                if 1000 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31:
                    if target_format == "iso":
                        return f"{year:04d}-{month:02d}-{day:02d}"
                    return f"{month:02d}/{day:02d}/{year:04d}"
            except ValueError:
                pass

    # Unparseable -- return unchanged
    return date_str


def normalize_occupation(occupation: str) -> str:
    """Normalize an occupation string to title case with acronym preservation.

    Applies smart_title_case in occupation mode, which preserves known
    professional acronyms (CEO, CPA, RN, CNC, MD, etc.) while converting
    the rest of the text to title case.

    Empty strings are returned unchanged.

    Args:
        occupation: The occupation string to normalize.

    Returns:
        Normalized occupation string.
    """
    if not occupation:
        return occupation

    return smart_title_case(occupation, is_occupation=True)
