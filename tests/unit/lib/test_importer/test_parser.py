"""Unit tests for importer parser module."""

import tempfile
from pathlib import Path

import pandas as pd

from voter_api.lib.importer.parser import detect_delimiter, detect_encoding, parse_csv_chunks


class TestDetectDelimiter:
    """Tests for delimiter detection."""

    def test_comma_delimiter(self, tmp_path: Path) -> None:
        """Detect comma delimiter."""
        f = tmp_path / "test.csv"
        f.write_text("County,Voter Registration #,Status\nFulton,12345,ACTIVE\n")
        assert detect_delimiter(f) == ","

    def test_pipe_delimiter(self, tmp_path: Path) -> None:
        """Detect pipe delimiter."""
        f = tmp_path / "test.csv"
        f.write_text("County|Voter Registration #|Status\nFulton|12345|ACTIVE\n")
        assert detect_delimiter(f) == "|"

    def test_tab_delimiter(self, tmp_path: Path) -> None:
        """Detect tab delimiter."""
        f = tmp_path / "test.csv"
        f.write_text("County\tVoter Registration #\tStatus\nFulton\t12345\tACTIVE\n")
        assert detect_delimiter(f) == "\t"


class TestDetectEncoding:
    """Tests for encoding detection."""

    def test_utf8(self, tmp_path: Path) -> None:
        """Detect UTF-8 encoding."""
        f = tmp_path / "test.csv"
        f.write_text("test data", encoding="utf-8")
        assert detect_encoding(f) == "utf-8"

    def test_latin1(self, tmp_path: Path) -> None:
        """Detect Latin-1 encoding when UTF-8 fails."""
        f = tmp_path / "test.csv"
        f.write_bytes(b"test \xe9 data\n")
        encoding = detect_encoding(f)
        assert encoding in ("utf-8", "latin-1")


class TestParseCsvChunks:
    """Tests for chunked CSV parsing."""

    def test_basic_parsing(self, tmp_path: Path) -> None:
        """Parse a basic CSV with column mapping."""
        f = tmp_path / "voters.csv"
        f.write_text(
            "County,Voter Registration #,Status,Last Name,First Name\n"
            "Fulton,12345,ACTIVE,SMITH,JOHN\n"
            "Fulton,12346,ACTIVE,DOE,JANE\n"
        )
        chunks = list(parse_csv_chunks(f, batch_size=10))
        assert len(chunks) == 1
        df = chunks[0]
        assert len(df) == 2
        assert "county" in df.columns
        assert "voter_registration_number" in df.columns
        assert df.iloc[0]["county"] == "Fulton"

    def test_chunked_reading(self, tmp_path: Path) -> None:
        """Reading respects batch_size for chunking."""
        f = tmp_path / "voters.csv"
        lines = ["County,Voter Registration #,Status,Last Name,First Name"]
        for i in range(10):
            lines.append(f"Fulton,{10000 + i},ACTIVE,LAST{i},FIRST{i}")
        f.write_text("\n".join(lines) + "\n")
        chunks = list(parse_csv_chunks(f, batch_size=3))
        assert len(chunks) == 4  # 10 / 3 = 3.33 → 4 chunks

    def test_empty_strings_become_none(self, tmp_path: Path) -> None:
        """Empty string values are converted to None."""
        f = tmp_path / "voters.csv"
        f.write_text(
            "County,Voter Registration #,Status,Last Name,First Name,Middle Name\n"
            "Fulton,12345,ACTIVE,SMITH,JOHN,\n"
        )
        chunks = list(parse_csv_chunks(f, batch_size=10))
        # pandas stores empty-string replacements as NaN internally
        assert pd.isna(chunks[0].iloc[0]["middle_name"])
