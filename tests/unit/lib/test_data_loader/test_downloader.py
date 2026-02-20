"""Unit tests for the file downloader."""

import hashlib
from pathlib import Path

import httpx
import pytest

from voter_api.lib.data_loader.downloader import (
    _compute_sha512,
    _is_cached,
    download_file,
    resolve_download_path,
)
from voter_api.lib.data_loader.types import DataFileEntry, FileCategory


class TestResolveDownloadPath:
    """Tests for resolve_download_path()."""

    def test_voter_goes_to_voter_subdir(self) -> None:
        entry = DataFileEntry(
            filename="Bibb-20260203.csv",
            sha512="a" * 128,
            category=FileCategory.VOTER,
            size_bytes=100,
        )
        result = resolve_download_path(entry, Path("data"))
        assert result == Path("data/voter/Bibb-20260203.csv")

    def test_boundary_goes_to_root(self) -> None:
        entry = DataFileEntry(
            filename="congress-2023-shape.zip",
            sha512="a" * 128,
            category=FileCategory.BOUNDARY,
            size_bytes=100,
        )
        result = resolve_download_path(entry, Path("data"))
        assert result == Path("data/congress-2023-shape.zip")

    def test_county_district_goes_to_root(self) -> None:
        entry = DataFileEntry(
            filename="counties-by-districts-2023.csv",
            sha512="a" * 128,
            category=FileCategory.COUNTY_DISTRICT,
            size_bytes=100,
        )
        result = resolve_download_path(entry, Path("data"))
        assert result == Path("data/counties-by-districts-2023.csv")

    def test_reference_goes_to_root(self) -> None:
        entry = DataFileEntry(
            filename="doc.pdf",
            sha512="a" * 128,
            category=FileCategory.REFERENCE,
            size_bytes=100,
        )
        result = resolve_download_path(entry, Path("data"))
        assert result == Path("data/doc.pdf")


class TestComputeSha512:
    """Tests for _compute_sha512()."""

    def test_computes_correct_hash(self, tmp_path: Path) -> None:
        content = b"hello world"
        file = tmp_path / "test.txt"
        file.write_bytes(content)

        expected = hashlib.sha512(content).hexdigest()
        assert _compute_sha512(file) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        file = tmp_path / "empty.txt"
        file.write_bytes(b"")

        expected = hashlib.sha512(b"").hexdigest()
        assert _compute_sha512(file) == expected


class TestIsCached:
    """Tests for _is_cached()."""

    def test_returns_true_when_checksum_matches(self, tmp_path: Path) -> None:
        content = b"test content"
        file = tmp_path / "test.zip"
        file.write_bytes(content)
        expected = hashlib.sha512(content).hexdigest()

        assert _is_cached(file, expected) is True

    def test_returns_false_when_checksum_differs(self, tmp_path: Path) -> None:
        file = tmp_path / "test.zip"
        file.write_bytes(b"test content")

        assert _is_cached(file, "b" * 128) is False

    def test_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        file = tmp_path / "nonexistent.zip"
        assert _is_cached(file, "a" * 128) is False


@pytest.mark.asyncio
class TestDownloadFile:
    """Tests for download_file()."""

    async def test_successful_download_with_checksum(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        content = b"file content here"
        sha = hashlib.sha512(content).hexdigest()
        dest = tmp_path / "test.zip"

        httpx_mock.add_response(
            url="https://data.example.com/test.zip",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/test.zip",
            dest=dest,
            expected_sha512=sha,
            size_bytes=len(content),
        )

        assert result.success is True
        assert result.downloaded is True
        assert result.verified is True
        assert result.local_path == dest
        assert dest.read_bytes() == content

    async def test_checksum_mismatch_discards_file(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        content = b"file content"
        dest = tmp_path / "bad.zip"

        httpx_mock.add_response(
            url="https://data.example.com/bad.zip",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/bad.zip",
            dest=dest,
            expected_sha512="f" * 128,
            size_bytes=len(content),
        )

        assert result.success is False
        assert "Checksum mismatch" in (result.error or "")
        assert not dest.exists()
        # .part file should also be cleaned up
        assert not dest.with_suffix(dest.suffix + ".part").exists()

    async def test_skip_if_cached(self, tmp_path: Path) -> None:
        content = b"cached content"
        sha = hashlib.sha512(content).hexdigest()
        dest = tmp_path / "cached.zip"
        dest.write_bytes(content)

        # No httpx mock needed — should not make any HTTP request
        result = await download_file(
            url="https://data.example.com/cached.zip",
            dest=dest,
            expected_sha512=sha,
            size_bytes=len(content),
        )

        assert result.success is True
        assert result.downloaded is False  # Skipped
        assert result.verified is True

    async def test_partial_download_cleanup(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        dest = tmp_path / "partial.zip"

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://data.example.com/partial.zip",
        )

        result = await download_file(
            url="https://data.example.com/partial.zip",
            dest=dest,
            expected_sha512="a" * 128,
            size_bytes=100,
        )

        assert result.success is False
        assert not dest.exists()
        assert not dest.with_suffix(dest.suffix + ".part").exists()

    async def test_creates_parent_directory(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        content = b"nested file"
        sha = hashlib.sha512(content).hexdigest()
        dest = tmp_path / "voter" / "test.csv"

        httpx_mock.add_response(
            url="https://data.example.com/test.csv",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/test.csv",
            dest=dest,
            expected_sha512=sha,
            size_bytes=len(content),
        )

        assert result.success is True
        assert dest.exists()

    async def test_skip_checksum_flag(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        content = b"no check"
        dest = tmp_path / "nocheck.zip"

        httpx_mock.add_response(
            url="https://data.example.com/nocheck.zip",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/nocheck.zip",
            dest=dest,
            expected_sha512="f" * 128,  # Wrong hash, but skipped
            size_bytes=len(content),
            skip_checksum=True,
        )

        assert result.success is True
        assert result.downloaded is True
        assert dest.exists()

    async def test_entry_passthrough(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        """When an entry is passed, the result uses it instead of a synthetic one."""
        content = b"entry test"
        sha = hashlib.sha512(content).hexdigest()
        dest = tmp_path / "entry.zip"
        real_entry = DataFileEntry(
            filename="entry.zip",
            sha512=sha,
            category=FileCategory.BOUNDARY,
            size_bytes=len(content),
        )

        httpx_mock.add_response(
            url="https://data.example.com/entry.zip",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/entry.zip",
            dest=dest,
            expected_sha512=sha,
            size_bytes=len(content),
            entry=real_entry,
        )

        assert result.success is True
        assert result.entry is real_entry
        assert result.entry.category == FileCategory.BOUNDARY

    async def test_default_synthetic_entry(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        """Without entry param, a synthetic REFERENCE entry is created."""
        content = b"synthetic test"
        sha = hashlib.sha512(content).hexdigest()
        dest = tmp_path / "synth.zip"

        httpx_mock.add_response(
            url="https://data.example.com/synth.zip",
            content=content,
        )

        result = await download_file(
            url="https://data.example.com/synth.zip",
            dest=dest,
            expected_sha512=sha,
            size_bytes=len(content),
        )

        assert result.success is True
        assert result.entry.category == FileCategory.REFERENCE

    async def test_http_error_response(
        self,
        tmp_path: Path,
        httpx_mock,  # type: ignore[no-untyped-def]
    ) -> None:
        dest = tmp_path / "error.zip"

        httpx_mock.add_response(
            url="https://data.example.com/error.zip",
            status_code=500,
        )

        result = await download_file(
            url="https://data.example.com/error.zip",
            dest=dest,
            expected_sha512="a" * 128,
            size_bytes=100,
        )

        assert result.success is False
        assert "Download failed" in (result.error or "")
