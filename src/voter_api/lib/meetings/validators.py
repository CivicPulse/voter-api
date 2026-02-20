"""Validation helpers for meeting record file uploads and video URLs.

Provides pure-function validators for file format acceptance, video URL
platform detection, and timestamp validation.
"""

from urllib.parse import urlparse

# Allowed MIME types for meeting attachments, mapped from file extensions.
ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/tiff": ".tiff",
}

# Reverse mapping: extension -> MIME type
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

# Video platform domain patterns
_YOUTUBE_DOMAINS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}
_VIMEO_DOMAINS = {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}


def validate_file_content_type(content_type: str) -> bool:
    """Check whether a MIME type is in the allowed list.

    Args:
        content_type: The MIME type string to validate.

    Returns:
        True if the content type is allowed, False otherwise.
    """
    return content_type.split(";")[0].strip().lower() in ALLOWED_MIME_TYPES


def validate_file_extension(filename: str) -> bool:
    """Check whether a filename has an allowed extension.

    Args:
        filename: The original filename to validate.

    Returns:
        True if the file extension is allowed, False otherwise.
    """
    ext = _extract_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def _extract_extension(filename: str) -> str:
    """Extract the lowercase file extension including the dot.

    Args:
        filename: The filename to extract from.

    Returns:
        The lowercase extension (e.g., ".pdf") or empty string if none.
    """
    dot_idx = filename.rfind(".")
    if dot_idx == -1:
        return ""
    return filename[dot_idx:].lower()


def get_allowed_extensions_display() -> str:
    """Return a human-readable string of allowed file extensions.

    Returns:
        Comma-separated list of allowed extensions.
    """
    unique_exts = sorted(set(ALLOWED_EXTENSIONS.keys()))
    return ", ".join(unique_exts)


def detect_video_platform(url: str) -> str | None:
    """Detect the video platform from a URL.

    Args:
        url: The video URL to check.

    Returns:
        "youtube" or "vimeo" if recognized, None otherwise.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
    except Exception:
        return None

    if hostname in _YOUTUBE_DOMAINS:
        return "youtube"
    if hostname in _VIMEO_DOMAINS:
        return "vimeo"
    return None


def validate_video_url(url: str) -> tuple[bool, str | None]:
    """Validate that a URL is from YouTube or Vimeo.

    Args:
        url: The video URL to validate.

    Returns:
        A tuple of (is_valid, platform). Platform is "youtube" or "vimeo"
        if valid, None otherwise.
    """
    platform = detect_video_platform(url)
    return (platform is not None, platform)


def validate_video_timestamps(
    start_seconds: int | None,
    end_seconds: int | None,
) -> bool:
    """Validate that video timestamps are logically consistent.

    Args:
        start_seconds: Optional start timestamp in seconds.
        end_seconds: Optional end timestamp in seconds.

    Returns:
        True if timestamps are valid (or both None), False otherwise.
    """
    if start_seconds is not None and start_seconds < 0:
        return False
    if end_seconds is not None and end_seconds < 0:
        return False
    if start_seconds is not None and end_seconds is not None:
        return end_seconds > start_seconds
    return True
