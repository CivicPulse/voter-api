"""Unit tests for voter history CSV parser module."""

from datetime import date
from pathlib import Path

import pytest

from voter_api.lib.voter_history.parser import (
    DEFAULT_ELECTION_TYPE,
    ELECTION_TYPE_MAP,
    GA_SOS_VOTER_HISTORY_COLUMN_MAP,
    generate_election_name,
    map_election_type,
    parse_voter_history_chunks,
)

# ---------------------------------------------------------------------------
# Sample CSV helpers
# ---------------------------------------------------------------------------

HEADER = (
    "County Name,Voter Registration Number,Election Date,"
    "Election Type,Party,Ballot Style,Absentee,Provisional,Supplemental"
)

VALID_ROW = "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"


def _write_csv(tmp_path: Path, rows: list[str], header: str = HEADER) -> Path:
    """Write a CSV file from header + rows."""
    f = tmp_path / "voter_history.csv"
    content = header + "\n" + "\n".join(rows) + "\n"
    f.write_text(content, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# Column map constant
# ---------------------------------------------------------------------------


class TestColumnMap:
    """Tests for the GA SoS column map constant."""

    def test_nine_columns(self) -> None:
        """Column map has exactly 9 entries."""
        assert len(GA_SOS_VOTER_HISTORY_COLUMN_MAP) == 9

    def test_expected_keys(self) -> None:
        """Column map includes all expected CSV header names."""
        expected = {
            "County Name",
            "Voter Registration Number",
            "Election Date",
            "Election Type",
            "Party",
            "Ballot Style",
            "Absentee",
            "Provisional",
            "Supplemental",
        }
        assert set(GA_SOS_VOTER_HISTORY_COLUMN_MAP.keys()) == expected


# ---------------------------------------------------------------------------
# Election type mapping (T030)
# ---------------------------------------------------------------------------


class TestMapElectionType:
    """Tests for election type normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("GENERAL ELECTION", "general"),
            ("GENERAL PRIMARY", "primary"),
            ("SPECIAL ELECTION", "special"),
            ("SPECIAL ELECTION RUNOFF", "runoff"),
            ("SPECIAL PRIMARY", "primary"),
            ("SPECIAL PRIMARY RUNOFF", "runoff"),
            ("PRESIDENTIAL PREFERENCE PRIMARY", "primary"),
        ],
    )
    def test_known_types(self, raw: str, expected: str) -> None:
        """All known GA SoS election types map correctly."""
        assert map_election_type(raw) == expected

    def test_unknown_type_defaults_to_general(self) -> None:
        """Unknown election types default to 'general'."""
        assert map_election_type("UNKNOWN TYPE") == DEFAULT_ELECTION_TYPE

    def test_case_insensitive(self) -> None:
        """Mapping is case-insensitive."""
        assert map_election_type("general election") == "general"
        assert map_election_type("General Election") == "general"

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        assert map_election_type("  GENERAL ELECTION  ") == "general"

    def test_all_map_entries_covered(self) -> None:
        """Every entry in ELECTION_TYPE_MAP produces a valid result."""
        for raw_type, expected in ELECTION_TYPE_MAP.items():
            assert map_election_type(raw_type) == expected


# ---------------------------------------------------------------------------
# Election name generation (T030)
# ---------------------------------------------------------------------------


class TestGenerateElectionName:
    """Tests for auto-created election name generation."""

    def test_general_election_name(self) -> None:
        """Generate name for a general election."""
        name = generate_election_name("GENERAL ELECTION", date(2024, 11, 5))
        assert name == "General Election - 11/05/2024"

    def test_primary_name(self) -> None:
        """Generate name for a primary."""
        name = generate_election_name("GENERAL PRIMARY", date(2024, 5, 21))
        assert name == "General Primary - 05/21/2024"

    def test_whitespace_stripped_and_titled(self) -> None:
        """Input is stripped and title-cased."""
        name = generate_election_name("  special election  ", date(2024, 1, 15))
        assert name == "Special Election - 01/15/2024"


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


class TestDateParsing:
    """Tests for date parsing within chunked records."""

    def test_valid_date(self, tmp_path: Path) -> None:
        """Valid MM/DD/YYYY date is parsed correctly."""
        f = _write_csv(tmp_path, [VALID_ROW])
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        record = chunks[0][0]
        assert record["election_date"] == date(2024, 11, 5)
        assert record["_parse_error"] is None

    def test_invalid_date_format(self, tmp_path: Path) -> None:
        """Invalid date format produces a parse error."""
        row = "FULTON,12345678,2024-11-05,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"
        f = _write_csv(tmp_path, [row])
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        record = chunks[0][0]
        assert record["_parse_error"] is not None
        assert "Invalid date" in record["_parse_error"]

    def test_empty_date_error(self, tmp_path: Path) -> None:
        """Missing election date produces a parse error."""
        row = "FULTON,12345678,,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"
        f = _write_csv(tmp_path, [row])
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        record = chunks[0][0]
        assert record["_parse_error"] is not None
        assert "Missing election_date" in record["_parse_error"]


# ---------------------------------------------------------------------------
# Boolean coercion
# ---------------------------------------------------------------------------


class TestBooleanCoercion:
    """Tests for boolean field parsing (Y/N/blank)."""

    def test_y_is_true(self, tmp_path: Path) -> None:
        """'Y' is parsed as True."""
        row = "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,Y,Y,Y"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["absentee"] is True
        assert record["provisional"] is True
        assert record["supplemental"] is True

    def test_n_is_false(self, tmp_path: Path) -> None:
        """'N' is parsed as False."""
        row = "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,N,N,N"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["absentee"] is False
        assert record["provisional"] is False
        assert record["supplemental"] is False

    def test_blank_is_false(self, tmp_path: Path) -> None:
        """Blank/empty boolean fields are parsed as False."""
        row = "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,,,"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["absentee"] is False
        assert record["provisional"] is False
        assert record["supplemental"] is False


# ---------------------------------------------------------------------------
# Chunked reading
# ---------------------------------------------------------------------------


class TestChunkedReading:
    """Tests for chunked iteration over large files."""

    def test_single_chunk(self, tmp_path: Path) -> None:
        """Small file yields a single chunk."""
        rows = [f"FULTON,{10000 + i},11/05/2024,GENERAL ELECTION,NP,STD,N,N,N" for i in range(5)]
        f = _write_csv(tmp_path, rows)
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert len(chunks[0]) == 5

    def test_multiple_chunks(self, tmp_path: Path) -> None:
        """File larger than batch_size yields multiple chunks."""
        rows = [f"FULTON,{10000 + i},11/05/2024,GENERAL ELECTION,NP,STD,N,N,N" for i in range(10)]
        f = _write_csv(tmp_path, rows)
        chunks = list(parse_voter_history_chunks(f, batch_size=3))
        assert len(chunks) == 4  # 10 / 3 = 3.33 → 4 chunks
        total_records = sum(len(c) for c in chunks)
        assert total_records == 10

    def test_custom_batch_size(self, tmp_path: Path) -> None:
        """batch_size parameter controls chunk size."""
        rows = [f"FULTON,{10000 + i},11/05/2024,GENERAL ELECTION,NP,STD,N,N,N" for i in range(6)]
        f = _write_csv(tmp_path, rows)
        chunks = list(parse_voter_history_chunks(f, batch_size=2))
        assert len(chunks) == 3
        for chunk in chunks:
            assert len(chunk) == 2


# ---------------------------------------------------------------------------
# Column mapping & field extraction
# ---------------------------------------------------------------------------


class TestColumnMapping:
    """Tests for CSV column mapping to model fields."""

    def test_all_fields_mapped(self, tmp_path: Path) -> None:
        """All 9 columns are mapped to model field names."""
        f = _write_csv(tmp_path, [VALID_ROW])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["voter_registration_number"] == "12345678"
        assert record["county"] == "FULTON"
        assert record["election_type"] == "GENERAL ELECTION"
        assert record["party"] == "NP"
        assert record["ballot_style"] == "BALLOT 1"

    def test_normalized_election_type_added(self, tmp_path: Path) -> None:
        """Records include the normalized_election_type field."""
        f = _write_csv(tmp_path, [VALID_ROW])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["normalized_election_type"] == "general"

    def test_optional_fields_nullable(self, tmp_path: Path) -> None:
        """Party and ballot_style are None when blank."""
        row = "FULTON,12345678,11/05/2024,GENERAL ELECTION,,,N,N,N"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["party"] is None
        assert record["ballot_style"] is None


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------


class TestMissingRequiredFields:
    """Tests for parse error on missing required fields."""

    def test_missing_registration_number(self, tmp_path: Path) -> None:
        """Missing voter_registration_number produces parse error."""
        row = "FULTON,,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["_parse_error"] is not None
        assert "voter_registration_number" in record["_parse_error"]

    def test_missing_county(self, tmp_path: Path) -> None:
        """Missing county produces parse error."""
        row = ",12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["_parse_error"] is not None
        assert "county" in record["_parse_error"]

    def test_missing_election_type(self, tmp_path: Path) -> None:
        """Missing election_type produces parse error."""
        row = "FULTON,12345678,11/05/2024,,NP,BALLOT 1,Y,N,N"
        f = _write_csv(tmp_path, [row])
        record = list(parse_voter_history_chunks(f, batch_size=10))[0][0]
        assert record["_parse_error"] is not None
        assert "election_type" in record["_parse_error"]


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------


class TestEncodingDetection:
    """Tests for encoding auto-detection."""

    def test_utf8_file(self, tmp_path: Path) -> None:
        """UTF-8 encoded file is parsed correctly."""
        f = _write_csv(tmp_path, [VALID_ROW])
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert chunks[0][0]["_parse_error"] is None

    def test_latin1_file(self, tmp_path: Path) -> None:
        """Latin-1 encoded file is parsed correctly."""
        f = tmp_path / "voter_history.csv"
        content = HEADER + "\n" + VALID_ROW + "\n"
        f.write_bytes(content.encode("latin-1"))
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert chunks[0][0]["_parse_error"] is None


# ---------------------------------------------------------------------------
# Delimiter detection
# ---------------------------------------------------------------------------


class TestDelimiterDetection:
    """Tests for delimiter auto-detection."""

    def test_pipe_delimiter(self, tmp_path: Path) -> None:
        """Pipe-delimited file is parsed correctly."""
        header = HEADER.replace(",", "|")
        row = VALID_ROW.replace(",", "|")
        f = tmp_path / "voter_history.csv"
        f.write_text(header + "\n" + row + "\n")
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert chunks[0][0]["voter_registration_number"] == "12345678"

    def test_tab_delimiter(self, tmp_path: Path) -> None:
        """Tab-delimited file is parsed correctly."""
        header = HEADER.replace(",", "\t")
        row = VALID_ROW.replace(",", "\t")
        f = tmp_path / "voter_history.csv"
        f.write_text(header + "\n" + row + "\n")
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert chunks[0][0]["voter_registration_number"] == "12345678"


# ---------------------------------------------------------------------------
# Empty / edge-case files
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge-case inputs."""

    def test_header_only_file(self, tmp_path: Path) -> None:
        """File with only a header yields no data records."""
        f = tmp_path / "voter_history.csv"
        f.write_text(HEADER + "\n")
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        total_records = sum(len(c) for c in chunks)
        assert total_records == 0

    def test_whitespace_in_headers(self, tmp_path: Path) -> None:
        """Headers with extra whitespace are stripped and mapped."""
        header = (
            " County Name , Voter Registration Number , Election Date ,"
            " Election Type , Party , Ballot Style , Absentee , Provisional , Supplemental "
        )
        row = "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,BALLOT 1,Y,N,N"
        f = tmp_path / "voter_history.csv"
        f.write_text(header + "\n" + row + "\n")
        chunks = list(parse_voter_history_chunks(f, batch_size=10))
        assert len(chunks) == 1
        assert chunks[0][0]["voter_registration_number"] == "12345678"
