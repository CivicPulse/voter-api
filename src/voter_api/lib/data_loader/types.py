"""Data types for the data_loader library.

Defines the in-memory structures for the remote seed manifest,
individual file entries, and download/import result tracking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path


class FileCategory(StrEnum):
    """Category of a data file in the seed manifest."""

    BOUNDARY = "boundary"
    VOTER = "voter"
    COUNTY_DISTRICT = "county_district"
    REFERENCE = "reference"


@dataclass(frozen=True)
class DataFileEntry:
    """A single file listed in the remote seed manifest.

    Attributes:
        filename: File name as it appears on the remote server.
        sha512: Expected SHA512 hex digest (lowercase, 128 hex characters).
        category: File category determining how the file is imported.
        size_bytes: File size in bytes.
    """

    filename: str
    sha512: str
    category: FileCategory
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.filename:
            msg = "filename must not be empty"
            raise ValueError(msg)
        if not re.fullmatch(r"[a-f0-9]{128}", self.sha512):
            msg = f"sha512 must be 128 lowercase hex characters, got {self.sha512!r:.32}"
            raise ValueError(msg)
        if self.size_bytes < 0:
            msg = "size_bytes must be non-negative"
            raise ValueError(msg)


@dataclass(frozen=True)
class SeedManifest:
    """Remote manifest.json fetched from the Data Root URL.

    Attributes:
        version: Manifest schema version (currently "1").
        updated_at: When the manifest was last updated.
        files: List of all available data files.
    """

    version: str
    updated_at: datetime
    files: tuple[DataFileEntry, ...]

    def __post_init__(self) -> None:
        if self.version != "1":
            msg = f"Unsupported manifest version: {self.version!r} (expected '1')"
            raise ValueError(msg)


@dataclass
class DownloadResult:
    """Tracks the outcome of downloading a single file.

    Attributes:
        entry: The manifest entry this result is for.
        downloaded: Whether the file was freshly downloaded (False = skipped/cached).
        verified: Whether checksum verification passed.
        local_path: Local filesystem path where the file is stored.
        error: Error message if download/verification failed, or None.
    """

    entry: DataFileEntry
    downloaded: bool = False
    verified: bool = False
    local_path: Path | None = None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Whether the download completed successfully."""
        return self.verified and self.error is None


@dataclass
class SeedResult:
    """Tracks the overall outcome of a seed operation.

    Attributes:
        downloads: Results for each file download.
        import_results: Keyed by category; import outcome per phase.
        total_downloaded_bytes: Total bytes freshly downloaded.
        total_skipped: Number of files skipped (already cached).
        success: True if all downloads and imports succeeded.
    """

    downloads: list[DownloadResult] = field(default_factory=list)
    import_results: dict[str, object] = field(default_factory=dict)
    total_downloaded_bytes: int = 0
    total_skipped: int = 0
    success: bool = True
