"""Publisher data types for static dataset publishing.

Dataclasses representing manifest entries, publish results, and manifest structure.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DatasetEntry:
    """Metadata for a single published dataset."""

    name: str
    key: str
    public_url: str
    content_type: str
    record_count: int
    file_size_bytes: int
    boundary_type: str | None
    filters: dict[str, str]
    published_at: datetime


@dataclass
class PublishResult:
    """Result of a publish operation."""

    datasets: list[DatasetEntry]
    manifest_key: str
    total_records: int
    total_size_bytes: int
    duration_seconds: float


@dataclass
class ManifestData:
    """Parsed manifest.json contents."""

    version: str
    published_at: datetime
    publisher_version: str
    datasets: dict[str, DatasetEntry] = field(default_factory=dict)
