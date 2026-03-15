"""Data types for the markdown-to-JSONL converter.

Defines the internal data structures used to pass parsed markdown
content through the converter pipeline. These types are independent
of Pydantic JSONL schemas and the database.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class FileType(enum.Enum):
    """Markdown file type classification."""

    OVERVIEW = "overview"
    SINGLE_CONTEST = "single_contest"
    MULTI_CONTEST = "multi_contest"


@dataclass
class ContestData:
    """Parsed data for a single contest section within a multi-contest file."""

    heading: str
    body_id: str | None = None
    seat_id: str | None = None
    candidates: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    """Result of parsing a markdown election file.

    Contains extracted metadata, contest data, and any validation
    errors or warnings encountered during parsing.
    """

    file_path: Path
    file_type: FileType
    metadata: dict[str, str] = field(default_factory=dict)
    contests: list[ContestData] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    calendar: dict[str, str] = field(default_factory=dict)
    heading: str = ""


@dataclass
class ConversionResult:
    """Result of converting a ParseResult to JSONL-ready records."""

    file_path: Path
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    file_type: FileType | None = None
