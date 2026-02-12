"""Pydantic v2 schemas for publish status and dataset discovery."""

from datetime import datetime

from pydantic import BaseModel, Field


class PublishedDatasetInfo(BaseModel):
    """Metadata for a single published dataset in the status response."""

    name: str = Field(description="Dataset name (e.g., 'congressional', 'all-boundaries')")
    key: str = Field(description="S3 object key")
    public_url: str = Field(description="Public URL for direct access")
    content_type: str = Field(default="application/geo+json", description="MIME type")
    record_count: int = Field(description="Number of boundary features in the file")
    file_size_bytes: int = Field(description="File size in bytes")
    boundary_type: str | None = Field(default=None, description="Boundary type filter (null for combined file)")
    published_at: datetime = Field(description="When this dataset was last published")


class PublishStatusResponse(BaseModel):
    """Response schema for the publish status endpoint."""

    configured: bool = Field(description="Whether R2/S3 publishing is configured")
    manifest_loaded: bool = Field(description="Whether a manifest has been successfully loaded")
    manifest_published_at: datetime | None = Field(default=None, description="When the manifest was last published")
    manifest_cached_at: datetime | None = Field(default=None, description="When the manifest was last fetched from R2")
    datasets: list[PublishedDatasetInfo] = Field(default_factory=list, description="Published dataset details")


class DiscoveredDataset(BaseModel):
    """A single dataset in the discovery response."""

    name: str = Field(description="Dataset name (e.g., 'congressional', 'all-boundaries')")
    url: str = Field(description="Full public URL for direct access")
    boundary_type: str | None = Field(default=None, description="Boundary type (null for combined file)")
    record_count: int = Field(description="Number of boundary features")


class DatasetDiscoveryResponse(BaseModel):
    """Response schema for the public dataset discovery endpoint."""

    base_url: str | None = Field(
        description="R2 public URL prefix for constructing paths. Null when R2 is not configured."
    )
    datasets: list[DiscoveredDataset] = Field(default_factory=list, description="Published datasets")
