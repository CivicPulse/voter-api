"""Internal data types for the normalizer library.

Defines the data structures used to represent normalization results
and file change records. These types are independent of the database
and have no I/O side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class NormalizationResult:
    """Result of normalizing a single field value.

    Attributes:
        original: The original value before normalization.
        normalized: The normalized value.
        changed: Whether the value was changed by normalization.
        rule: The name of the normalization rule that was applied.
    """

    original: str
    normalized: str
    changed: bool
    rule: str = ""


@dataclass
class FileChange:
    """Record of a change made to a field within a file.

    Attributes:
        field_name: The name of the field that was changed.
        original: The original field value.
        normalized: The normalized field value.
        rule: The normalization rule applied.
    """

    field_name: str
    original: str
    normalized: str
    rule: str = ""


@dataclass
class FileNormalizationResult:
    """Result of normalizing a single file.

    Attributes:
        file_path: Path to the processed file.
        changes: List of individual field changes made.
        errors: List of error messages if normalization failed.
        warnings: List of warning messages.
        uuid_generated: Whether a new UUID was generated for this file.
        renamed_to: New path if the file was renamed, else None.
    """

    file_path: Path
    changes: list[FileChange] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    uuid_generated: bool = False
    renamed_to: Path | None = None
