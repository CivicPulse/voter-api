"""Tests for the PDF election calendar preprocessor."""

from pathlib import Path

import pytest

from voter_api.lib.election_calendar.parser import parse_calendar_jsonl
from voter_api.lib.election_calendar.pdf_preprocessor import (
    _is_data_row,
    _parse_advance_voting_range,
    _parse_date_flex,
    _parse_registration_deadline,
    preprocess_pdf_calendar,
)

# Path to the actual PDF test file
_ACTUAL_PDF = Path("data/new/2026 Short Calendar .pdf")


class TestParseDateFlex:
    """Tests for flexible date parsing."""

    def test_mmddyyyy(self) -> None:
        """MM/DD/YYYY format is parsed."""
        assert _parse_date_flex("05/19/2026") is not None
        assert str(_parse_date_flex("05/19/2026")) == "2026-05-19"

    def test_mmddyy(self) -> None:
        """MM/DD/YY format is parsed with 2000s century."""
        assert _parse_date_flex("04/27/26") is not None
        assert str(_parse_date_flex("04/27/26")) == "2026-04-27"

    def test_invalid_returns_none(self) -> None:
        """Non-date strings return None."""
        assert _parse_date_flex("not a date") is None
        assert _parse_date_flex("") is None


class TestParseAdvanceVotingRange:
    """Tests for advance voting range parsing."""

    def test_simple_range(self) -> None:
        """Simple date range with dash separator."""
        start, end = _parse_advance_voting_range("04/27/26 - 05/15/26")
        assert str(start) == "2026-04-27"
        assert str(end) == "2026-05-15"

    def test_range_with_preamble(self) -> None:
        """Range prefixed with 'As soon as possible' text."""
        text = "As soon as possible, but no later than 06/08/26 - 06/12/26"
        start, end = _parse_advance_voting_range(text)
        assert str(start) == "2026-06-08"
        assert str(end) == "2026-06-12"

    def test_no_dates_returns_none(self) -> None:
        """Text with no dates returns (None, None)."""
        start, end = _parse_advance_voting_range("no dates here")
        assert start is None
        assert end is None


class TestParseRegistrationDeadline:
    """Tests for registration deadline parsing."""

    def test_simple_date(self) -> None:
        """Single date is returned."""
        assert str(_parse_registration_deadline("04/20/2026")) == "2026-04-20"

    def test_multiline_with_federal(self) -> None:
        """Primary deadline is returned, federal (*) skipped."""
        text = "04/20/2026\n*05/18/2026"
        assert str(_parse_registration_deadline(text)) == "2026-04-20"


class TestIsDataRow:
    """Tests for the data row detection helper."""

    def test_data_row_detected(self) -> None:
        """Row with election name and date is a data row."""
        row = ["General Primary", None, "05/19/2026", None, "04/27/26 - 05/15/26"]
        assert _is_data_row(row) is True

    def test_header_row_rejected(self) -> None:
        """Header row with 'ELECTION DATE' is not a data row."""
        row = ["ELECTION", None, "ELECTION DATE", None, "ADVANCE VOTING DATES"]
        assert _is_data_row(row) is False

    def test_empty_row_rejected(self) -> None:
        """Empty row is not a data row."""
        row = [None, None, None, None]
        assert _is_data_row(row) is False


@pytest.mark.skipif(
    not (_ACTUAL_PDF).exists(),
    reason="Actual PDF test file not available",
)
class TestPreprocessActualPdf:
    """Integration test against the real GA SoS PDF calendar."""

    def test_extracts_entries_from_real_pdf(self, tmp_path: Path) -> None:
        """The real PDF produces at least 3 calendar entries."""
        output_path = tmp_path / "output.jsonl"
        count = preprocess_pdf_calendar(_ACTUAL_PDF, output_path)

        assert count >= 3
        entries = parse_calendar_jsonl(output_path)
        assert len(entries) >= 3

        # Verify we got known elections
        names = [e.election_name for e in entries]
        # Should contain some variant of primary and general
        name_text = " ".join(names).lower()
        assert "primary" in name_text or "general" in name_text

    def test_dates_are_in_2026(self, tmp_path: Path) -> None:
        """All extracted dates are in year 2026."""
        output_path = tmp_path / "output.jsonl"
        preprocess_pdf_calendar(_ACTUAL_PDF, output_path)
        entries = parse_calendar_jsonl(output_path)

        for entry in entries:
            assert entry.election_date.year == 2026
            if entry.registration_deadline:
                assert entry.registration_deadline.year == 2026
