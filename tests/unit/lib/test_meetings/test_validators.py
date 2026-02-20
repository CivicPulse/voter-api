"""Unit tests for meeting record validators."""

import pytest

from voter_api.lib.meetings.validators import (
    detect_video_platform,
    get_allowed_extensions_display,
    validate_file_content_type,
    validate_file_extension,
    validate_video_timestamps,
    validate_video_url,
)


class TestFileContentTypeValidation:
    """Tests for MIME type validation."""

    @pytest.mark.parametrize(
        "content_type",
        [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/csv",
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/tiff",
        ],
    )
    def test_allowed_content_types(self, content_type: str) -> None:
        """Allowed MIME types should be accepted."""
        assert validate_file_content_type(content_type) is True

    @pytest.mark.parametrize(
        "content_type",
        [
            "application/octet-stream",
            "application/x-executable",
            "text/html",
            "application/javascript",
            "application/zip",
        ],
    )
    def test_rejected_content_types(self, content_type: str) -> None:
        """Disallowed MIME types should be rejected."""
        assert validate_file_content_type(content_type) is False

    def test_case_insensitive(self) -> None:
        """MIME type validation should be case-insensitive."""
        assert validate_file_content_type("Application/PDF") is True
        assert validate_file_content_type("IMAGE/JPEG") is True


class TestFileExtensionValidation:
    """Tests for filename extension validation."""

    @pytest.mark.parametrize(
        "filename",
        [
            "agenda.pdf",
            "minutes.doc",
            "report.docx",
            "budget.xls",
            "data.xlsx",
            "records.csv",
            "photo.png",
            "image.jpg",
            "image.jpeg",
            "logo.gif",
            "scan.tif",
            "document.tiff",
        ],
    )
    def test_allowed_extensions(self, filename: str) -> None:
        """Files with allowed extensions should be accepted."""
        assert validate_file_extension(filename) is True

    @pytest.mark.parametrize(
        "filename",
        [
            "malware.exe",
            "script.sh",
            "page.html",
            "code.js",
            "archive.zip",
            "noextension",
        ],
    )
    def test_rejected_extensions(self, filename: str) -> None:
        """Files with disallowed extensions should be rejected."""
        assert validate_file_extension(filename) is False

    def test_case_insensitive(self) -> None:
        """Extension validation should be case-insensitive."""
        assert validate_file_extension("REPORT.PDF") is True
        assert validate_file_extension("Data.XLSX") is True


class TestAllowedExtensionsDisplay:
    """Tests for human-readable extensions list."""

    def test_returns_string(self) -> None:
        """Should return a comma-separated string."""
        result = get_allowed_extensions_display()
        assert isinstance(result, str)
        assert ".pdf" in result
        assert ".docx" in result

    def test_sorted(self) -> None:
        """Extensions should be sorted alphabetically."""
        result = get_allowed_extensions_display()
        parts = [p.strip() for p in result.split(",")]
        assert parts == sorted(parts)


class TestVideoUrlValidation:
    """Tests for video URL validation and platform detection."""

    @pytest.mark.parametrize(
        ("url", "expected_platform"),
        [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
            ("https://youtube.com/watch?v=abc123", "youtube"),
            ("https://youtu.be/abc123", "youtube"),
            ("https://m.youtube.com/watch?v=abc123", "youtube"),
        ],
    )
    def test_youtube_urls(self, url: str, expected_platform: str) -> None:
        """YouTube URLs should be recognized."""
        is_valid, platform = validate_video_url(url)
        assert is_valid is True
        assert platform == expected_platform

    @pytest.mark.parametrize(
        ("url", "expected_platform"),
        [
            ("https://vimeo.com/123456789", "vimeo"),
            ("https://www.vimeo.com/123456789", "vimeo"),
            ("https://player.vimeo.com/video/123456789", "vimeo"),
        ],
    )
    def test_vimeo_urls(self, url: str, expected_platform: str) -> None:
        """Vimeo URLs should be recognized."""
        is_valid, platform = validate_video_url(url)
        assert is_valid is True
        assert platform == expected_platform

    @pytest.mark.parametrize(
        "url",
        [
            "https://dailymotion.com/video/abc123",
            "https://example.com/video",
            "https://tiktok.com/@user/video/123",
            "not-a-url",
            "",
        ],
    )
    def test_invalid_urls(self, url: str) -> None:
        """Non-YouTube/Vimeo URLs should be rejected."""
        is_valid, platform = validate_video_url(url)
        assert is_valid is False
        assert platform is None

    def test_detect_video_platform_youtube(self) -> None:
        """detect_video_platform should return 'youtube' for YouTube URLs."""
        assert detect_video_platform("https://www.youtube.com/watch?v=abc") == "youtube"

    def test_detect_video_platform_vimeo(self) -> None:
        """detect_video_platform should return 'vimeo' for Vimeo URLs."""
        assert detect_video_platform("https://vimeo.com/123") == "vimeo"

    def test_detect_video_platform_unknown(self) -> None:
        """detect_video_platform should return None for unknown domains."""
        assert detect_video_platform("https://example.com/video") is None


class TestVideoTimestamps:
    """Tests for video timestamp validation."""

    def test_both_none(self) -> None:
        """Both timestamps None should be valid."""
        assert validate_video_timestamps(None, None) is True

    def test_start_only(self) -> None:
        """Start-only timestamp should be valid."""
        assert validate_video_timestamps(60, None) is True

    def test_end_only(self) -> None:
        """End-only timestamp should be valid."""
        assert validate_video_timestamps(None, 120) is True

    def test_valid_range(self) -> None:
        """End after start should be valid."""
        assert validate_video_timestamps(60, 120) is True

    def test_end_before_start(self) -> None:
        """End before start should be invalid."""
        assert validate_video_timestamps(120, 60) is False

    def test_equal_timestamps(self) -> None:
        """Equal timestamps should be invalid (end must be > start)."""
        assert validate_video_timestamps(60, 60) is False

    def test_negative_start(self) -> None:
        """Negative start should be invalid."""
        assert validate_video_timestamps(-1, 60) is False

    def test_negative_end(self) -> None:
        """Negative end should be invalid."""
        assert validate_video_timestamps(0, -1) is False

    def test_zero_start(self) -> None:
        """Zero start should be valid."""
        assert validate_video_timestamps(0, 60) is True
