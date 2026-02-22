"""Meeting records library — file validation and storage abstractions.

Public API:
    - ``validate_file_content_type``: Check if a MIME type is allowed
    - ``validate_file_extension``: Check if a filename extension is allowed
    - ``get_allowed_extensions_display``: Human-readable list of allowed extensions
    - ``detect_video_platform``: Detect YouTube/Vimeo from a URL
    - ``validate_video_url``: Validate and detect platform from a URL
    - ``validate_video_timestamps``: Check timestamp consistency
    - ``FileStorage``: Protocol for file storage backends
    - ``LocalFileStorage``: Local filesystem storage implementation
"""

from voter_api.lib.meetings.storage import FileStorage, LocalFileStorage
from voter_api.lib.meetings.validators import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    detect_video_platform,
    get_allowed_extensions_display,
    validate_file_content_type,
    validate_file_extension,
    validate_video_timestamps,
    validate_video_url,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "ALLOWED_MIME_TYPES",
    "FileStorage",
    "LocalFileStorage",
    "detect_video_platform",
    "get_allowed_extensions_display",
    "validate_file_content_type",
    "validate_file_extension",
    "validate_video_timestamps",
    "validate_video_url",
]
