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
- normalize_directory and normalize_file for file-level processing

No database dependency -- processes files in memory and writes results
only when explicitly requested.
"""

from __future__ import annotations

from voter_api.lib.normalizer.normalize import detect_file_type, normalize_directory, normalize_file
from voter_api.lib.normalizer.report import NormalizationReport
from voter_api.lib.normalizer.title_case import smart_title_case

__all__ = [
    "detect_file_type",
    "normalize_directory",
    "normalize_file",
    "NormalizationReport",
    "smart_title_case",
]
