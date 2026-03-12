"""Tests for voter_api.lib.csv_utils shared CSV utilities."""

from datetime import date
from pathlib import Path

import pytest

from voter_api.lib.csv_utils import (
    detect_delimiter,
    detect_encoding,
    normalize_registration_number,
    parse_date_iso,
    parse_date_mdy,
    parse_yes_no_bool,
)

# ---------------------------------------------------------------------------
# detect_delimiter
# ---------------------------------------------------------------------------


class TestDetectDelimiter:
    """Tests for detect_delimiter()."""

    def test_comma_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "comma.csv"
        f.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        assert detect_delimiter(f) == ","

    def test_pipe_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "pipe.csv"
        f.write_text("a|b|c\n1|2|3\n", encoding="utf-8")
        assert detect_delimiter(f) == "|"

    def test_tab_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "tab.csv"
        f.write_text("a\tb\tc\n1\t2\t3\n", encoding="utf-8")
        assert detect_delimiter(f) == "\t"

    def test_error_on_no_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.csv"
        f.write_text("nodelmiterhere\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot detect delimiter"):
            detect_delimiter(f)


# ---------------------------------------------------------------------------
# detect_encoding
# ---------------------------------------------------------------------------


class TestDetectEncoding:
    """Tests for detect_encoding()."""

    def test_utf8(self, tmp_path: Path) -> None:
        f = tmp_path / "utf8.csv"
        f.write_text("hello,world\n", encoding="utf-8")
        assert detect_encoding(f) == "utf-8"

    def test_latin1(self, tmp_path: Path) -> None:
        f = tmp_path / "latin1.csv"
        # Write raw bytes that are valid Latin-1 but invalid UTF-8
        f.write_bytes(b"caf\xe9,latt\xe9\n")
        assert detect_encoding(f) == "latin-1"

    def test_error_on_binary(self, tmp_path: Path) -> None:
        """Binary garbage that is valid in latin-1 still returns latin-1.

        Since latin-1 accepts all byte values 0x00-0xFF, detect_encoding
        will always fall back to latin-1 rather than raising.
        """
        f = tmp_path / "binary.bin"
        f.write_bytes(bytes(range(256)))
        # latin-1 accepts all single-byte values, so this should succeed
        assert detect_encoding(f) == "latin-1"


# ---------------------------------------------------------------------------
# normalize_registration_number (re-export)
# ---------------------------------------------------------------------------


class TestNormalizeRegistrationNumber:
    """Tests for normalize_registration_number() re-export."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("00013148", "13148"),
            ("0001", "1"),
            ("0000", "0"),
            ("000", "0"),
            ("42", "42"),
            ("0", "0"),
        ],
    )
    def test_strip_leading_zeros(self, input_val: str, expected: str) -> None:
        assert normalize_registration_number(input_val) == expected


# ---------------------------------------------------------------------------
# parse_yes_no_bool
# ---------------------------------------------------------------------------


class TestParseYesNoBool:
    """Tests for parse_yes_no_bool()."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("Y", True),
            ("y", True),
            (" y ", True),
            ("N", False),
            ("n", False),
            (" N ", False),
            ("", None),
            ("  ", None),
            (None, None),
        ],
    )
    def test_values(self, input_val: str | None, expected: bool | None) -> None:
        assert parse_yes_no_bool(input_val) is expected

    def test_unexpected_value_returns_none(self) -> None:
        assert parse_yes_no_bool("maybe") is None


# ---------------------------------------------------------------------------
# parse_date_mdy
# ---------------------------------------------------------------------------


class TestParseDateMdy:
    """Tests for parse_date_mdy()."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("03/02/2026", date(2026, 3, 2)),
            ("12/31/1999", date(1999, 12, 31)),
            ("01/01/2000", date(2000, 1, 1)),
            ("", None),
            ("  ", None),
            (None, None),
            ("not-a-date", None),
            ("2026-03-02", None),  # wrong format
            ("13/01/2026", None),  # invalid month
        ],
    )
    def test_values(self, input_val: str | None, expected: date | None) -> None:
        assert parse_date_mdy(input_val) == expected


# ---------------------------------------------------------------------------
# parse_date_iso
# ---------------------------------------------------------------------------


class TestParseDateIso:
    """Tests for parse_date_iso()."""

    @pytest.mark.parametrize(
        ("input_val", "expected"),
        [
            ("2026-03-02", date(2026, 3, 2)),
            ("1999-12-31", date(1999, 12, 31)),
            ("2000-01-01", date(2000, 1, 1)),
            ("", None),
            ("  ", None),
            (None, None),
            ("not-a-date", None),
            ("03/02/2026", None),  # wrong format
        ],
    )
    def test_values(self, input_val: str | None, expected: date | None) -> None:
        assert parse_date_iso(input_val) == expected
