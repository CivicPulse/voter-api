"""Shared CSV utilities for delimiter/encoding detection, date and boolean parsing.

Extracted from the voter and voter-history parsers to eliminate duplication
and provide a single source of truth for common CSV operations.
"""

from datetime import date
from pathlib import Path

from loguru import logger

from voter_api.lib.normalize import normalize_registration_number

# Re-export for convenience so callers can import from one place.
__all__ = [
    "detect_delimiter",
    "detect_encoding",
    "normalize_registration_number",
    "parse_date_iso",
    "parse_date_mdy",
    "parse_yes_no_bool",
]


def detect_delimiter(file_path: Path) -> str:
    """Detect the CSV delimiter by reading the first line.

    Tries UTF-8 first, then Latin-1. Counts occurrences of comma, pipe,
    and tab characters and returns whichever appears most often.

    Args:
        file_path: Path to the CSV file.

    Returns:
        The detected delimiter character.

    Raises:
        ValueError: If the delimiter cannot be detected.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            with file_path.open("r", encoding=encoding) as f:
                first_line = f.readline()
            break
        except UnicodeDecodeError:
            continue
    else:
        msg = f"Cannot detect encoding for {file_path}"
        raise ValueError(msg)

    # Count delimiter candidates
    counts = {
        ",": first_line.count(","),
        "|": first_line.count("|"),
        "\t": first_line.count("\t"),
    }
    delimiter = max(counts, key=counts.get)  # type: ignore[arg-type]
    if counts[delimiter] == 0:
        msg = f"Cannot detect delimiter in {file_path}"
        raise ValueError(msg)

    logger.debug(f"Detected delimiter: {delimiter!r} for {file_path}")
    return delimiter


def detect_encoding(file_path: Path) -> str:
    """Detect file encoding by attempting to read with common encodings.

    Tries UTF-8 first (reading the first 8 KiB), then falls back to Latin-1.

    Args:
        file_path: Path to the CSV file.

    Returns:
        The detected encoding string.

    Raises:
        ValueError: If encoding cannot be detected.
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            with file_path.open("r", encoding=encoding) as f:
                f.read(8192)
            return encoding
        except UnicodeDecodeError:
            continue
    msg = f"Cannot detect encoding for {file_path}"
    raise ValueError(msg)


def parse_yes_no_bool(value: str | None) -> bool | None:
    """Convert a Y/N string to a boolean.

    Args:
        value: String value, typically ``"Y"`` or ``"N"``.

    Returns:
        ``True`` for ``"Y"``/``"y"``, ``False`` for ``"N"``/``"n"``,
        ``None`` for empty string or ``None``.
    """
    if value is None:
        return None
    cleaned = value.strip().upper()
    if cleaned == "Y":
        return True
    if cleaned == "N":
        return False
    if cleaned == "":
        return None
    return None


def parse_date_mdy(value: str | None) -> date | None:
    """Parse a date in MM/DD/YYYY format.

    Args:
        value: Date string in ``MM/DD/YYYY`` format.

    Returns:
        A :class:`datetime.date` instance, or ``None`` if the value is
        empty, ``None``, or unparseable.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parts = cleaned.split("/")
        if len(parts) != 3:
            return None
        month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def parse_date_iso(value: str | None) -> date | None:
    """Parse a date in YYYY-MM-DD (ISO 8601) format.

    Args:
        value: Date string in ``YYYY-MM-DD`` format.

    Returns:
        A :class:`datetime.date` instance, or ``None`` if the value is
        empty, ``None``, or unparseable.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None
