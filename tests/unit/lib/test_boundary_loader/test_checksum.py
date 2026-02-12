"""Unit tests for SHA512 checksum verification."""

import hashlib
from pathlib import Path

import pytest

from voter_api.lib.boundary_loader.checksum import verify_sha512


class TestVerifySha512:
    """Tests for verify_sha512 function."""

    def test_valid_checksum_passes(self, tmp_path: Path) -> None:
        """Verification passes when checksum matches."""
        data = b"test boundary data content"
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(data)

        expected_hash = hashlib.sha512(data).hexdigest()
        checksum_path = tmp_path / "test.zip.sha512.txt"
        checksum_path.write_text(f"{expected_hash}  test.zip\n")

        assert verify_sha512(file_path) is True

    def test_invalid_checksum_raises(self, tmp_path: Path) -> None:
        """Verification raises ValueError when checksum does not match."""
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(b"actual content")

        checksum_path = tmp_path / "test.zip.sha512.txt"
        checksum_path.write_text("0000deadbeef0000  test.zip\n")

        with pytest.raises(ValueError, match="SHA512 mismatch"):
            verify_sha512(file_path)

    def test_missing_checksum_file_returns_true(self, tmp_path: Path) -> None:
        """Returns True with warning when no checksum file exists."""
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(b"some data")

        assert verify_sha512(file_path) is True

    def test_checksum_case_insensitive(self, tmp_path: Path) -> None:
        """Verification is case-insensitive for hex digests."""
        data = b"case test"
        file_path = tmp_path / "test.zip"
        file_path.write_bytes(data)

        expected_hash = hashlib.sha512(data).hexdigest().upper()
        checksum_path = tmp_path / "test.zip.sha512.txt"
        checksum_path.write_text(f"{expected_hash}  test.zip\n")

        assert verify_sha512(file_path) is True
