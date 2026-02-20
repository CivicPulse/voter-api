"""Unit tests for data_loader type definitions."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from voter_api.lib.data_loader.types import (
    DataFileEntry,
    DownloadResult,
    FileCategory,
    SeedManifest,
    SeedResult,
)


class TestFileCategory:
    """Tests for the FileCategory enum."""

    def test_all_categories_exist(self) -> None:
        assert FileCategory.BOUNDARY == "boundary"
        assert FileCategory.VOTER == "voter"
        assert FileCategory.COUNTY_DISTRICT == "county_district"
        assert FileCategory.REFERENCE == "reference"

    def test_category_from_string(self) -> None:
        assert FileCategory("boundary") == FileCategory.BOUNDARY
        assert FileCategory("voter") == FileCategory.VOTER
        assert FileCategory("county_district") == FileCategory.COUNTY_DISTRICT
        assert FileCategory("reference") == FileCategory.REFERENCE

    def test_invalid_category_raises(self) -> None:
        with pytest.raises(ValueError, match="'invalid'"):
            FileCategory("invalid")


class TestDataFileEntry:
    """Tests for the DataFileEntry dataclass."""

    def test_valid_entry(self) -> None:
        entry = DataFileEntry(
            filename="test.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=1024,
        )
        assert entry.filename == "test.zip"
        assert entry.sha512 == "a" * 128
        assert entry.category == FileCategory.BOUNDARY
        assert entry.size_bytes == 1024

    def test_empty_filename_raises(self) -> None:
        with pytest.raises(ValueError, match="filename must not be empty"):
            DataFileEntry(
                filename="",
                sha512="a" * 128,
                category=FileCategory.BOUNDARY,
                size_bytes=0,
            )

    def test_invalid_sha512_length_raises(self) -> None:
        with pytest.raises(ValueError, match="sha512 must be 128 hex characters"):
            DataFileEntry(
                filename="test.zip",
                sha512="abc",
                category=FileCategory.BOUNDARY,
                size_bytes=0,
            )

    def test_negative_size_raises(self) -> None:
        with pytest.raises(ValueError, match="size_bytes must be non-negative"):
            DataFileEntry(
                filename="test.zip",
                sha512="a" * 128,
                category=FileCategory.BOUNDARY,
                size_bytes=-1,
            )

    def test_frozen(self) -> None:
        entry = DataFileEntry(
            filename="test.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=0,
        )
        with pytest.raises(AttributeError):
            entry.filename = "other.zip"  # type: ignore[misc]


class TestSeedManifest:
    """Tests for the SeedManifest dataclass."""

    def test_valid_manifest(self) -> None:
        entry = DataFileEntry(
            filename="test.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=100,
        )
        manifest = SeedManifest(
            version="1",
            updated_at=datetime(2026, 2, 20, tzinfo=UTC),
            files=(entry,),
        )
        assert manifest.version == "1"
        assert len(manifest.files) == 1

    def test_empty_files_allowed(self) -> None:
        manifest = SeedManifest(
            version="1",
            updated_at=datetime(2026, 2, 20, tzinfo=UTC),
            files=(),
        )
        assert len(manifest.files) == 0

    def test_unsupported_version_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported manifest version"):
            SeedManifest(
                version="2",
                updated_at=datetime(2026, 2, 20, tzinfo=UTC),
                files=(),
            )


class TestDownloadResult:
    """Tests for the DownloadResult dataclass."""

    def _make_entry(self) -> DataFileEntry:
        return DataFileEntry(
            filename="test.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=100,
        )

    def test_default_state(self) -> None:
        result = DownloadResult(entry=self._make_entry())
        assert result.downloaded is False
        assert result.verified is False
        assert result.local_path is None
        assert result.error is None
        assert result.success is False

    def test_success_state(self) -> None:
        result = DownloadResult(
            entry=self._make_entry(),
            downloaded=True,
            verified=True,
            local_path=Path("/data/test.zip"),
        )
        assert result.success is True

    def test_error_state(self) -> None:
        result = DownloadResult(
            entry=self._make_entry(),
            verified=True,
            error="Connection refused",
        )
        assert result.success is False

    def test_unverified_not_success(self) -> None:
        result = DownloadResult(
            entry=self._make_entry(),
            downloaded=True,
            verified=False,
        )
        assert result.success is False


class TestSeedResult:
    """Tests for the SeedResult dataclass."""

    def test_default_state(self) -> None:
        result = SeedResult()
        assert result.downloads == []
        assert result.import_results == {}
        assert result.total_downloaded_bytes == 0
        assert result.total_skipped == 0
        assert result.success is True

    def test_mutable_fields(self) -> None:
        result = SeedResult()
        entry = DataFileEntry(
            filename="test.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=100,
        )
        result.downloads.append(DownloadResult(entry=entry))
        assert len(result.downloads) == 1
