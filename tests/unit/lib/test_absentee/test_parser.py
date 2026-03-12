"""Tests for the GA SoS absentee ballot application CSV parser."""

from datetime import date
from pathlib import Path

import pytest

from voter_api.lib.absentee.parser import (
    GA_SOS_ABSENTEE_COLUMN_MAP,
    _parse_yes_no_bool,
    parse_absentee_csv_chunks,
)

# Full CSV header line matching the 38-column GA SoS format
CSV_HEADER = (
    "County,Voter Registration #,Last Name,First Name,Middle Name,Suffix,"
    "Street #,Street Name,Apt/Unit,City,State,Zip Code,"
    "Mailing Street #,Mailing Street Name,Mailing Apt/Unit,Mailing City,"
    "Mailing State,Mailing Zip Code,Application Status,Ballot Status,"
    "Status Reason,Application Date,Ballot Issued Date,Ballot Return Date,"
    "Ballot Style,Ballot Assisted,Challenged/Provisional,ID Required,"
    "Municipal Precinct,County Precinct,CNG,SEN,HOUSE,JUD,"
    "Combo #,Vote Center ID,Ballot ID,Party"
)

# Complete valid data row
VALID_ROW = (
    "BACON,00468991,DELETTRE,GERALD,L,,171,LACY NORTON RD,,NICHOLLS,GA,"
    "31554-3841,171,LACY NORTON RD,,NICHOLLS,GA,31554-3841,A,,"
    "APPLICATION ACCEPTED,03/03/2026,,,ABSENTEE BY MAIL,NO,NO,NO,,"
    "DOUGLAS,001,019,178,WAYC,00005,,0030121009006,REPUBLICAN"
)

# Row with all date and boolean fields populated
FULL_ROW = (
    "FULTON,00123456,SMITH,JANE,M,JR,100,MAIN ST,APT 4,ATLANTA,GA,"
    "30301,200,ELM ST,SUITE B,ATLANTA,GA,30302,A,I,"
    "BALLOT ISSUED,01/15/2026,01/20/2026,01/25/2026,IN PERSON,YES,YES,YES,"
    "MP1,NORTH,005,034,055,ATLA,00010,VC123,0050340550001,DEMOCRATIC"
)


def _write_csv(tmp_path: Path, rows: list[str], encoding: str = "utf-8") -> Path:
    """Helper to write a CSV file with the standard header."""
    csv_path = tmp_path / "absentee.csv"
    content = "\n".join([CSV_HEADER, *rows]) + "\n"
    csv_path.write_text(content, encoding=encoding)
    return csv_path


class TestParseValidCSV:
    """Test parsing a valid CSV with all 38 columns."""

    def test_parses_valid_row(self, tmp_path: Path) -> None:
        """A complete valid row should parse without errors."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))

        assert len(chunks) == 1
        records = chunks[0]
        assert len(records) == 1

        rec = records[0]
        assert rec["_parse_error"] is None
        assert rec["county"] == "BACON"
        assert rec["voter_registration_number"] == "468991"
        assert rec["last_name"] == "DELETTRE"
        assert rec["first_name"] == "GERALD"
        assert rec["middle_name"] == "L"
        assert rec["application_status"] == "A"
        assert rec["status_reason"] == "APPLICATION ACCEPTED"
        assert rec["ballot_style"] == "ABSENTEE BY MAIL"
        assert rec["party"] == "REPUBLICAN"
        assert rec["congressional_district"] == "001"
        assert rec["state_senate_district"] == "019"
        assert rec["state_house_district"] == "178"
        assert rec["judicial_district"] == "WAYC"
        assert rec["ballot_id"] == "0030121009006"

    def test_parses_full_row_with_all_fields(self, tmp_path: Path) -> None:
        """A row with every field populated should parse completely."""
        csv_path = _write_csv(tmp_path, [FULL_ROW])
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        rec = chunks[0][0]

        assert rec["_parse_error"] is None
        assert rec["suffix"] == "JR"
        assert rec["apt_unit"] == "APT 4"
        assert rec["mailing_apt_unit"] == "SUITE B"
        assert rec["ballot_status"] == "I"
        assert rec["municipal_precinct"] == "MP1"
        assert rec["combo"] == "00010"
        assert rec["vote_center_id"] == "VC123"


class TestMissingOptionalFields:
    """Test parsing with missing optional fields."""

    def test_empty_optional_fields_are_none(self, tmp_path: Path) -> None:
        """Empty optional fields should be converted to None."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        rec = chunks[0][0]

        assert rec["suffix"] is None
        assert rec["apt_unit"] is None
        assert rec["ballot_status"] is None
        assert rec["ballot_issued_date"] is None
        assert rec["ballot_return_date"] is None
        assert rec["municipal_precinct"] is None
        assert rec["vote_center_id"] is None


class TestVoterRegistrationNormalization:
    """Test voter registration number normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("00468991", "468991"),
            ("00000001", "1"),
            ("12345678", "12345678"),
            ("00000000", "0"),
        ],
    )
    def test_registration_number_strip_leading_zeros(self, tmp_path: Path, raw: str, expected: str) -> None:
        """Leading zeros should be stripped from voter registration numbers."""
        row = VALID_ROW.replace("00468991", raw)
        csv_path = _write_csv(tmp_path, [row])
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        assert chunks[0][0]["voter_registration_number"] == expected


class TestDateParsing:
    """Test date parsing (MM/DD/YYYY → date objects)."""

    def test_application_date_parsed(self, tmp_path: Path) -> None:
        """Application date should be parsed to a date object."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        assert chunks[0][0]["application_date"] == date(2026, 3, 3)

    def test_all_dates_parsed(self, tmp_path: Path) -> None:
        """All three date fields should be parsed when present."""
        csv_path = _write_csv(tmp_path, [FULL_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["application_date"] == date(2026, 1, 15)
        assert rec["ballot_issued_date"] == date(2026, 1, 20)
        assert rec["ballot_return_date"] == date(2026, 1, 25)

    def test_empty_dates_are_none(self, tmp_path: Path) -> None:
        """Empty date fields should be None."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["ballot_issued_date"] is None
        assert rec["ballot_return_date"] is None


class TestBooleanParsing:
    """Test boolean parsing (YES/NO → True/False, empty → None)."""

    def test_no_values_parse_to_false(self, tmp_path: Path) -> None:
        """NO values should parse to False."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["ballot_assisted"] is False
        assert rec["challenged_provisional"] is False
        assert rec["id_required"] is False

    def test_yes_values_parse_to_true(self, tmp_path: Path) -> None:
        """YES values should parse to True."""
        csv_path = _write_csv(tmp_path, [FULL_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["ballot_assisted"] is True
        assert rec["challenged_provisional"] is True
        assert rec["id_required"] is True

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("YES", True),
            ("yes", True),
            ("Y", True),
            ("NO", False),
            ("no", False),
            ("N", False),
            ("", None),
            (None, None),
        ],
    )
    def test_parse_yes_no_bool(self, value: str | None, expected: bool | None) -> None:
        """The _parse_yes_no_bool helper should handle various inputs."""
        assert _parse_yes_no_bool(value) == expected


class TestRequiredFieldValidation:
    """Test that missing required fields produce _parse_error."""

    def test_missing_voter_registration_number(self, tmp_path: Path) -> None:
        """Missing voter registration number should set _parse_error."""
        # Replace the reg number with empty
        row = VALID_ROW.replace("00468991", "")
        csv_path = _write_csv(tmp_path, [row])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["_parse_error"] is not None
        assert "voter_registration_number" in rec["_parse_error"]

    def test_missing_county(self, tmp_path: Path) -> None:
        """Missing county should set _parse_error."""
        # Replace "BACON," at the start with ","
        row = ",00468991," + VALID_ROW.split(",", 2)[2]
        csv_path = _write_csv(tmp_path, [row])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        assert rec["_parse_error"] is not None
        assert "county" in rec["_parse_error"]

    def test_valid_row_has_no_parse_error(self, tmp_path: Path) -> None:
        """A valid row should have _parse_error = None."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]
        assert rec["_parse_error"] is None


class TestBatchChunking:
    """Test that chunking produces the expected number of batches."""

    def test_chunking_produces_correct_batches(self, tmp_path: Path) -> None:
        """10 rows with batch_size=3 should produce 4 chunks (3+3+3+1)."""
        rows = [VALID_ROW] * 10
        csv_path = _write_csv(tmp_path, rows)
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=3))

        assert len(chunks) == 4
        assert len(chunks[0]) == 3
        assert len(chunks[1]) == 3
        assert len(chunks[2]) == 3
        assert len(chunks[3]) == 1

    def test_single_chunk_when_batch_exceeds_rows(self, tmp_path: Path) -> None:
        """When batch_size exceeds row count, only one chunk is produced."""
        rows = [VALID_ROW] * 5
        csv_path = _write_csv(tmp_path, rows)
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))

        assert len(chunks) == 1
        assert len(chunks[0]) == 5


class TestColumnMapping:
    """Test that all 38 columns are mapped correctly."""

    def test_column_map_has_38_entries(self) -> None:
        """The column map should have exactly 38 entries."""
        assert len(GA_SOS_ABSENTEE_COLUMN_MAP) == 38

    def test_all_csv_headers_are_mapped(self) -> None:
        """Every CSV header should have a mapping."""
        csv_headers = [h.strip() for h in CSV_HEADER.split(",")]
        assert len(csv_headers) == 38
        for header in csv_headers:
            assert header in GA_SOS_ABSENTEE_COLUMN_MAP, f"Missing mapping for: {header}"

    def test_all_mapped_fields_present_in_output(self, tmp_path: Path) -> None:
        """Every mapped field should appear in the output record dict."""
        csv_path = _write_csv(tmp_path, [FULL_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        for model_field in GA_SOS_ABSENTEE_COLUMN_MAP.values():
            assert model_field in rec, f"Missing field in output: {model_field}"


class TestEmptyStringConversion:
    """Test that empty strings are converted to None."""

    def test_empty_strings_become_none(self, tmp_path: Path) -> None:
        """Fields with empty strings in the CSV should be None in output."""
        csv_path = _write_csv(tmp_path, [VALID_ROW])
        rec = list(parse_absentee_csv_chunks(csv_path, batch_size=100))[0][0]

        # These fields are empty in VALID_ROW
        assert rec["suffix"] is None
        assert rec["apt_unit"] is None
        assert rec["mailing_apt_unit"] is None
        assert rec["ballot_status"] is None
        assert rec["municipal_precinct"] is None
        assert rec["vote_center_id"] is None


class TestEncodingDetection:
    """Test that files with different encodings are read correctly."""

    def test_latin1_encoded_file(self, tmp_path: Path) -> None:
        """A Latin-1 encoded file should be parsed correctly."""
        # Use a name with a Latin-1 character (e.g., accented e)
        row = VALID_ROW.replace("DELETTRE", "DELETTR\u00c9")
        csv_path = _write_csv(tmp_path, [row], encoding="latin-1")
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        rec = chunks[0][0]

        assert rec["_parse_error"] is None
        assert rec["last_name"] == "DELETTR\u00c9"

    def test_utf8_encoded_file(self, tmp_path: Path) -> None:
        """A UTF-8 encoded file should be parsed correctly."""
        csv_path = _write_csv(tmp_path, [VALID_ROW], encoding="utf-8")
        chunks = list(parse_absentee_csv_chunks(csv_path, batch_size=100))
        assert len(chunks[0]) == 1
        assert chunks[0][0]["_parse_error"] is None
