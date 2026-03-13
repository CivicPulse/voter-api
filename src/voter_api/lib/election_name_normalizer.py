"""Election name normalization for deduplication.

Standardizes election names from SoS feeds and candidate imports to prevent
duplicate election records caused by formatting variations.
"""

import re


def normalize_election_name(name: str | None) -> str | None:
    """Normalize an election name for consistent storage.

    Transformations applied:
    1. Replace en-dashes and em-dashes with hyphens.
    2. Standardize date formats (e.g., "January 5, 2021" -> "Jan 05, 2021").
    3. Expand common abbreviations (e.g., "Gen" -> "General", "Prim" -> "Primary").
    4. Collapse multiple spaces.
    5. Strip leading/trailing whitespace.

    Args:
        name: Raw election name from data source, or None.

    Returns:
        Normalized election name, or None/empty string if input was None/empty.
    """
    if not name:
        return name

    result = name

    # Replace en-dash and em-dash with hyphen
    result = result.replace("\u2013", "-").replace("\u2014", "-")

    # Standardize month names to 3-letter abbreviations
    # Use word boundaries to avoid corrupting place names (e.g., "Augusta")
    month_map = {
        "January": "Jan",
        "February": "Feb",
        "March": "Mar",
        "April": "Apr",
        "May": "May",
        "June": "Jun",
        "July": "Jul",
        "August": "Aug",
        "September": "Sep",
        "October": "Oct",
        "November": "Nov",
        "December": "Dec",
    }
    for full, abbr in month_map.items():
        result = re.sub(rf"\b{full}\b", abbr, result)

    # Standardize single-digit days to zero-padded (e.g., "Jan 5," -> "Jan 05,")
    result = re.sub(
        r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s+(\d),",
        r"\1 0\2,",
        result,
    )

    # Expand common election type abbreviations (word-boundary aware)
    abbreviations = {
        r"\bGen\b": "General",
        r"\bPrim\b": "Primary",
        r"\bElec\b": "Election",
        r"\bSpec\b": "Special",
    }
    for pattern, replacement in abbreviations.items():
        result = re.sub(pattern, replacement, result)

    # Collapse multiple spaces
    return re.sub(r"\s+", " ", result).strip()
