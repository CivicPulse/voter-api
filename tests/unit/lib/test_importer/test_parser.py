"""Unit tests for importer parser module."""

from pathlib import Path

import pandas as pd
import pytest
from loguru import logger

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

    def test_no_delimiter_raises(self, tmp_path: Path) -> None:
        """Raise ValueError when no delimiter can be detected."""
        f = tmp_path / "test.csv"
        f.write_text("single_column_no_delimiter\n")
        with pytest.raises(ValueError, match="Cannot detect delimiter"):
            detect_delimiter(f)


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

    def test_alternate_header_names(self, tmp_path: Path) -> None:
        """Parse CSV with alternate GA SoS header variants."""
        f = tmp_path / "voters.csv"
        f.write_text(
            "County,Voter Registration Number,Status,Last Name,First Name,"
            "Residence Apt Unit Number,Date of Last Contact,Mailing Apt Unit Number\n"
            "Fulton,12345,ACTIVE,SMITH,JOHN,APT 1,1/1/2025,APT 2\n"
        )
        chunks = list(parse_csv_chunks(f, batch_size=10))
        assert len(chunks) == 1
        df = chunks[0]
        assert "voter_registration_number" in df.columns
        assert "residence_apt_unit_number" in df.columns
        assert "date_of_last_contact" in df.columns
        assert "mailing_apt_unit_number" in df.columns
        assert df.iloc[0]["voter_registration_number"] == "12345"

    def test_empty_strings_become_none(self, tmp_path: Path) -> None:
        """Empty string values are converted to None."""
        f = tmp_path / "voters.csv"
        f.write_text(
            "County,Voter Registration #,Status,Last Name,First Name,Middle Name\nFulton,12345,ACTIVE,SMITH,JOHN,\n"
        )
        chunks = list(parse_csv_chunks(f, batch_size=10))
        # pandas stores empty-string replacements as NaN internally
        assert pd.isna(chunks[0].iloc[0]["middle_name"])

    def test_case_insensitive_header_matching(self, tmp_path: Path) -> None:
        """District columns with all-caps or mixed-case headers are mapped correctly.

        Regression test for the bug where GA SoS files with uppercase district
        column headers (e.g. 'CONGRESSIONAL DISTRICT') caused those fields to be
        silently dropped, resulting in null district values on every voter record.
        """
        f = tmp_path / "voters.csv"
        f.write_text(
            "COUNTY,VOTER REGISTRATION #,STATUS,LAST NAME,FIRST NAME,"
            "CONGRESSIONAL DISTRICT,STATE SENATE DISTRICT,STATE HOUSE DISTRICT,"
            "COUNTY PRECINCT\n"
            "Fulton,12345,ACTIVE,SMITH,JOHN,7,40,75,1A\n"
        )
        chunks = list(parse_csv_chunks(f, batch_size=10))
        assert len(chunks) == 1
        df = chunks[0]
        assert "congressional_district" in df.columns, "congressional_district must be mapped from all-caps header"
        assert "state_senate_district" in df.columns, "state_senate_district must be mapped from all-caps header"
        assert "state_house_district" in df.columns, "state_house_district must be mapped from all-caps header"
        assert "county_precinct" in df.columns, "county_precinct must be mapped from all-caps header"
        assert df.iloc[0]["congressional_district"] == "7"
        assert df.iloc[0]["state_senate_district"] == "40"
        assert df.iloc[0]["state_house_district"] == "75"
        assert df.iloc[0]["county_precinct"] == "1A"

    def test_unknown_columns_raise_error(self, tmp_path: Path) -> None:
        """Columns not in GA_SOS_COLUMN_MAP cause the import to halt with a bug report.

        The GA SoS voter file format is considered authoritative. Any column that
        cannot be mapped (even via case-insensitive fallback) indicates a potential
        file format change. The import halts immediately to prevent data loss, and
        the exception message contains a copy-paste-ready GitHub issue body.
        """
        f = tmp_path / "voters.csv"
        f.write_text(
            "County,Voter Registration #,Status,Last Name,First Name,ExtraColumn\n"
            "Fulton,12345,ACTIVE,SMITH,JOHN,somevalue\n"
        )
        with pytest.raises(ValueError, match="BUG REPORT") as exc_info:
            list(parse_csv_chunks(f, batch_size=10))

        error_msg = str(exc_info.value)
        assert "ExtraColumn" in error_msg, "Bug report must name the unknown column"
        assert "https://github.com/CivicPulse/voter-api/issues/new" in error_msg, (
            "Bug report must include the GitHub issue URL"
        )
        assert str(f) in error_msg, "Bug report must include the file path"

    def test_multiple_unknown_columns_all_named_in_error(self, tmp_path: Path) -> None:
        """All unknown columns are listed in the bug report, not just the first one."""
        f = tmp_path / "voters.csv"
        f.write_text("County,NewFieldA,NewFieldB,Status\nFulton,val1,val2,ACTIVE\n")
        with pytest.raises(ValueError, match="BUG REPORT") as exc_info:
            list(parse_csv_chunks(f, batch_size=10))

        error_msg = str(exc_info.value)
        assert "NewFieldA" in error_msg
        assert "NewFieldB" in error_msg

    def test_warning_logged_on_case_insensitive_match(self, tmp_path: Path) -> None:
        """A WARNING is emitted when a column matches only via case-insensitive fallback.

        The warning is the primary observability mechanism for this fix — it alerts
        operators that GA_SOS_COLUMN_MAP should be updated with the exact-case header.
        """
        f = tmp_path / "voters.csv"
        f.write_text("COUNTY,CONGRESSIONAL DISTRICT\nFulton,7\n")
        captured: list[str] = []
        handler_id = logger.add(lambda msg: captured.append(msg), level="WARNING", format="{level}: {message}")
        try:
            list(parse_csv_chunks(f, batch_size=10))
        finally:
            logger.remove(handler_id)

        assert any("case-insensitive fallback" in msg for msg in captured), (
            "Expected a WARNING log mentioning 'case-insensitive fallback' when a column header "
            "matches only via lowercase comparison"
        )
