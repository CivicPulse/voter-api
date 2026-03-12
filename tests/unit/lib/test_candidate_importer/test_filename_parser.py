"""Tests for candidate importer filename parser."""

from datetime import date

import pytest

from voter_api.lib.candidate_importer.filename_parser import (
    CandidateFileInfo,
    parse_candidate_filename,
)


class TestActualFilenames:
    """Parse the three real filenames from the SOS website."""

    @pytest.mark.parametrize(
        ("filename", "expected_date", "expected_type"),
        [
            (
                "MARCH_10_2026-SPECIAL_ELECTION_Qualified_Candidates.csv",
                date(2026, 3, 10),
                "special",
            ),
            (
                "MARCH_17_2026-SPECIAL_ELECTION_Qualified_Candidates.csv",
                date(2026, 3, 17),
                "special",
            ),
            (
                "MAY_19_2026-GENERAL_AND_PRIMARY_ELECTION_Qualified_Candidates.csv",
                date(2026, 5, 19),
                "general_primary",
            ),
        ],
        ids=["march-10-special", "march-17-special", "may-19-general-primary"],
    )
    def test_real_filename(self, filename: str, expected_date: date, expected_type: str) -> None:
        result = parse_candidate_filename(filename)

        assert isinstance(result, CandidateFileInfo)
        assert result.election_date == expected_date
        assert result.election_type == expected_type
        assert result.original_filename == filename


class TestElectionTypeMappings:
    """Every known election type string maps to the correct short name."""

    @pytest.mark.parametrize(
        ("type_fragment", "expected"),
        [
            ("SPECIAL_ELECTION", "special"),
            ("GENERAL_AND_PRIMARY_ELECTION", "general_primary"),
            ("PRIMARY_ELECTION", "primary"),
            ("GENERAL_ELECTION", "general"),
            ("RUNOFF_ELECTION", "runoff"),
        ],
        ids=["special", "general-primary", "primary", "general", "runoff"],
    )
    def test_election_type_mapping(self, type_fragment: str, expected: str) -> None:
        filename = f"JANUARY_1_2026-{type_fragment}_Qualified_Candidates.csv"
        result = parse_candidate_filename(filename)

        assert result.election_type == expected


class TestMonthNames:
    """Various month names parse correctly."""

    @pytest.mark.parametrize(
        ("month_name", "month_number"),
        [
            ("JANUARY", 1),
            ("FEBRUARY", 2),
            ("MARCH", 3),
            ("APRIL", 4),
            ("MAY", 5),
            ("JUNE", 6),
            ("JULY", 7),
            ("AUGUST", 8),
            ("SEPTEMBER", 9),
            ("OCTOBER", 10),
            ("NOVEMBER", 11),
            ("DECEMBER", 12),
        ],
    )
    def test_month_name(self, month_name: str, month_number: int) -> None:
        filename = f"{month_name}_15_2026-GENERAL_ELECTION_Qualified_Candidates.csv"
        result = parse_candidate_filename(filename)

        assert result.election_date.month == month_number
        assert result.election_date.day == 15
        assert result.election_date.year == 2026


class TestInvalidFilenames:
    """Invalid filenames raise ValueError."""

    def test_wrong_suffix(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("voters.csv")

    def test_missing_parts(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("MARCH_2026_Qualified_Candidates.csv")

    def test_bad_month_name(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("NOTAMONTH_10_2026-SPECIAL_ELECTION_Qualified_Candidates.csv")

    def test_invalid_date(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("FEBRUARY_30_2026-SPECIAL_ELECTION_Qualified_Candidates.csv")

    def test_empty_string(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("")

    def test_unknown_election_type(self) -> None:
        with pytest.raises(ValueError):
            parse_candidate_filename("MARCH_10_2026-FAKE_ELECTION_Qualified_Candidates.csv")


class TestFullPathInput:
    """Full file paths should work by extracting the basename."""

    def test_absolute_path(self) -> None:
        path = "/data/new/MARCH_10_2026-SPECIAL_ELECTION_Qualified_Candidates.csv"
        result = parse_candidate_filename(path)

        assert result.election_date == date(2026, 3, 10)
        assert result.election_type == "special"

    def test_relative_path(self) -> None:
        path = "data/new/MARCH_17_2026-SPECIAL_ELECTION_Qualified_Candidates.csv"
        result = parse_candidate_filename(path)

        assert result.election_date == date(2026, 3, 17)
        assert result.election_type == "special"
