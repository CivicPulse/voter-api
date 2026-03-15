"""Unit tests for individual normalization rule functions."""

from __future__ import annotations

import pytest

from voter_api.lib.normalizer.rules import (
    normalize_date,
    normalize_occupation,
    normalize_url,
)


class TestNormalizeUrl:
    """Tests for the normalize_url function."""

    @pytest.mark.parametrize(
        "input_url, expected",
        [
            # Add https:// to www domain without protocol
            ("WWW.EXAMPLE.COM", "https://www.example.com"),
            # Upgrade http to https, lowercase
            ("http://Example.COM", "https://example.com"),
            # Already correct -- unchanged
            ("https://example.com", "https://example.com"),
            # Dash placeholder -- unchanged
            ("--", "--"),
            # Empty string -- unchanged
            ("", ""),
            # Whitespace-only -- unchanged
            ("   ", "   "),
            # Em-dash placeholder -- unchanged
            ("\u2014", "\u2014"),
        ],
    )
    def test_url_normalization(self, input_url: str, expected: str) -> None:
        """Test URL normalization cases."""
        result = normalize_url(input_url)
        assert result == expected, f"normalize_url({input_url!r}) = {result!r}, expected {expected!r}"

    def test_adds_https_scheme(self) -> None:
        """URLs without protocol should get https://."""
        result = normalize_url("example.com")
        assert result.startswith("https://")

    def test_lowercases_domain(self) -> None:
        """Domain should be lowercased."""
        result = normalize_url("https://EXAMPLE.COM/PATH")
        assert result == "https://example.com/path"


class TestNormalizeDate:
    """Tests for the normalize_date function."""

    @pytest.mark.parametrize(
        "input_date, expected",
        [
            # Single-digit month/day -- zero-pad
            ("1/5/2026", "01/05/2026"),
            # ISO format to slash format
            ("2026-01-05", "01/05/2026"),
            # Already correct slash format
            ("01/05/2026", "01/05/2026"),
            # ISO with single digits
            ("2026-1-5", "01/05/2026"),
            # Dash placeholder -- unchanged
            ("--", "--"),
            # Unparseable -- unchanged
            ("invalid", "invalid"),
        ],
    )
    def test_date_normalization_slash_format(self, input_date: str, expected: str) -> None:
        """Test date normalization to slash format (default)."""
        result = normalize_date(input_date)
        assert result == expected, f"normalize_date({input_date!r}) = {result!r}, expected {expected!r}"

    def test_slash_to_iso_format(self) -> None:
        """Test conversion from slash format to ISO format."""
        result = normalize_date("01/05/2026", target_format="iso")
        assert result == "2026-01-05"

    def test_iso_to_iso_format(self) -> None:
        """Test ISO input remains ISO when target is iso."""
        result = normalize_date("2026-01-05", target_format="iso")
        assert result == "2026-01-05"

    def test_empty_string_unchanged(self) -> None:
        """Empty string should pass through unchanged."""
        result = normalize_date("")
        assert result == ""

    def test_placeholder_unchanged(self) -> None:
        """Dash placeholder should pass through unchanged."""
        result = normalize_date("--")
        assert result == "--"


class TestNormalizeOccupation:
    """Tests for the normalize_occupation function."""

    @pytest.mark.parametrize(
        "input_occ, expected",
        [
            # Basic title case
            ("SOFTWARE ENGINEER", "Software Engineer"),
            # Acronym preservation
            ("CNC MACHINIST", "CNC Machinist"),
            # Common text
            ("NOT EMPLOYED", "Not Employed"),
            # Empty -- unchanged
            ("", ""),
        ],
    )
    def test_occupation_normalization(self, input_occ: str, expected: str) -> None:
        """Test occupation normalization cases."""
        result = normalize_occupation(input_occ)
        assert result == expected, f"normalize_occupation({input_occ!r}) = {result!r}, expected {expected!r}"

    def test_rn_acronym_preserved(self) -> None:
        """RN (Registered Nurse) acronym should be preserved."""
        result = normalize_occupation("RN SUPERVISOR")
        assert result == "RN Supervisor"

    def test_ceo_acronym_preserved(self) -> None:
        """CEO acronym should be preserved."""
        result = normalize_occupation("CEO")
        assert result == "CEO"
