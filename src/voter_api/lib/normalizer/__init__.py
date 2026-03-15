"""Normalizer library for election and candidate markdown data.

Public API for normalizing AI-generated markdown files. Every rule is a
pure function with no side effects or file I/O. The library is designed
to be used both as a standalone tool and integrated into the import
pipeline.

Provides:
- Smart title case with SOS-specific edge case handling
- URL normalization (https upgrade, lowercase, placeholder passthrough)
- Date format normalization (slash <-> ISO, zero-padding)
- Occupation formatting with acronym preservation
- NormalizationReport for terminal and JSON reporting

No database dependency -- processes files in memory and writes results
only when explicitly requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from voter_api.lib.normalizer.report import NormalizationReport
from voter_api.lib.normalizer.title_case import smart_title_case

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "normalize_directory",
    "normalize_file",
    "NormalizationReport",
    "smart_title_case",
]


def normalize_directory(
    directory: Path,
    output: Path | None = None,
    fail_fast: bool = False,
) -> NormalizationReport:
    """Normalize all markdown files in a directory.

    Walks the directory tree, applies normalization rules to each
    markdown file, and writes corrected files in place (or to output
    directory if specified).

    Args:
        directory: Path to the directory to normalize.
        output: Optional output directory. If None, files are normalized
            in place.
        fail_fast: If True, stop on first failure.

    Returns:
        NormalizationReport with aggregate results.
    """
    raise NotImplementedError("normalize_directory is implemented in a later plan")


def normalize_file(
    file_path: Path,
    output: Path | None = None,
) -> NormalizationReport:
    """Normalize a single markdown file.

    Applies all normalization rules to the file's fields and writes
    the corrected content.

    Args:
        file_path: Path to the markdown file to normalize.
        output: Optional output path. If None, normalizes in place.

    Returns:
        NormalizationReport with results for this file.
    """
    raise NotImplementedError("normalize_file is implemented in a later plan")
