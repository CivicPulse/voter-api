"""UUID generation and candidate file renaming utilities.

Handles the lifecycle of UUIDs in candidate markdown files: detecting
whether a UUID is present, generating one if missing, and renaming
placeholder filenames to use the assigned UUID prefix.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


# Matches a valid UUID v4 (any version accepted for forward compatibility)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Placeholder values that signal "no UUID yet"
_EMPTY_PLACEHOLDERS: frozenset[str] = frozenset({"", "--", "\u2014", "-"})

# The 8-zero placeholder used in generated candidate filenames
_FILENAME_PLACEHOLDER = "00000000"


def ensure_uuid(content: str) -> tuple[str, str | None]:
    """Ensure a markdown file has a valid UUID in its ID metadata field.

    Reads the ``| ID | ... |`` row from the metadata table. If the value
    is empty or a placeholder (``--``, em-dash), generates a new UUID v4,
    inserts it into the content, and returns the updated content with the
    generated UUID string.

    If the ID is already a valid UUID, returns the content unchanged with
    ``None`` as the second element.

    Args:
        content: Markdown file content (string).

    Returns:
        Tuple of ``(updated_content, generated_uuid_str_or_None)``.
        ``generated_uuid_str_or_None`` is the newly generated UUID string
        if one was created, or ``None`` if the ID was already valid.

    Raises:
        ValueError: If the ID field contains a non-empty, non-placeholder
            value that is not a valid UUID.
    """
    pattern = r"\|\s*ID\s*\|\s*(.*?)\s*\|"
    match = re.search(pattern, content)

    if not match:
        # No ID field found -- treat as missing, generate UUID
        new_uuid = str(uuid.uuid4())
        return content, new_uuid

    id_value = match.group(1).strip()

    if id_value in _EMPTY_PLACEHOLDERS:
        # Missing UUID -- generate one
        new_uuid = str(uuid.uuid4())
        new_content = re.sub(
            r"(\|\s*ID\s*\|)\s*.*?\s*(\|)",
            rf"\g<1> {new_uuid} \2",
            content,
            count=1,
        )
        return new_content, new_uuid

    if _UUID_RE.match(id_value):
        # Already a valid UUID
        return content, None

    # Non-empty value that is not a valid UUID
    raise ValueError(
        f"ID field contains invalid UUID: {id_value!r}. "
        "Expected a valid UUID v4 or a placeholder (empty / -- / em-dash)."
    )


def rename_candidate_file(file_path: Path, uuid_str: str) -> Path | None:
    """Rename a candidate file whose name contains the 00000000 placeholder.

    If the filename contains ``00000000``, replaces it with the first 8
    characters of the provided UUID string and renames the file on disk.

    Args:
        file_path: Path to the candidate markdown file.
        uuid_str: The UUID string to use for the rename (full UUID,
            dashes included).

    Returns:
        The new ``Path`` if the file was renamed, or ``None`` if the
        filename did not contain the placeholder.
    """
    if _FILENAME_PLACEHOLDER not in file_path.name:
        return None

    # First 8 hex chars of UUID (no dashes)
    uuid_prefix = uuid_str.replace("-", "")[:8]
    new_name = file_path.name.replace(_FILENAME_PLACEHOLDER, uuid_prefix, 1)
    new_path = file_path.parent / new_name

    file_path.rename(new_path)
    return new_path
