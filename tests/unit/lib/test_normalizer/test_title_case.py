"""Unit tests for smart_title_case function."""

from __future__ import annotations

import pytest

from voter_api.lib.normalizer.title_case import smart_title_case


class TestSmartTitleCase:
    """Tests for the smart_title_case function."""

    @pytest.mark.parametrize(
        "input_text, expected",
        [
            # Suffixes (III, Jr, Sr)
            ("JOHN A COWAN JR", "John A. Cowan Jr"),
            ("DAVID LAFAYETTE MINCEY III", "David Lafayette Mincey III"),
            # Hyphenated names
            ("LISA WILLIAMS GARRETT-BOYD", "Lisa Williams Garrett-Boyd"),
            # Scottish Mc prefix
            ("CARLOS ANTONIO MCCLOUD", "Carlos Antonio McCloud"),
            # O' prefix
            ("MARY O'BRIEN", "Mary O'Brien"),
            # Mac prefix
            ("JAMES MACARTHUR", "James MacArthur"),
            # Lowercase articles/prepositions
            ("ROBERT DE LA CRUZ", "Robert de la Cruz"),
            # Governing body title with lowercase articles
            ("BOARD OF EDUCATION AT LARGE", "Board of Education at Large"),
            # Empty string
            ("", ""),
            # Already title case -- idempotent
            ("John A. Cowan Jr", "John A. Cowan Jr"),
            ("Mary O'Brien", "Mary O'Brien"),
        ],
    )
    def test_name_cases(self, input_text: str, expected: str) -> None:
        """Test smart title case for name inputs."""
        result = smart_title_case(input_text)
        assert result == expected, f"smart_title_case({input_text!r}) = {result!r}, expected {expected!r}"

    @pytest.mark.parametrize(
        "input_text, expected",
        [
            # Basic occupation
            ("SOFTWARE ENGINEER", "Software Engineer"),
            # Acronym preservation
            ("CNC MACHINIST", "CNC Machinist"),
            # Acronym at start with conjunction
            ("CEO AND FOUNDER", "CEO and Founder"),
            # Regular words
            ("RETIRED EDUCATOR", "Retired Educator"),
            # Two words
            ("NOT EMPLOYED", "Not Employed"),
            # Empty
            ("", ""),
        ],
    )
    def test_occupation_mode(self, input_text: str, expected: str) -> None:
        """Test smart title case in occupation mode."""
        result = smart_title_case(input_text, is_occupation=True)
        assert result == expected, f"smart_title_case({input_text!r}, is_occupation=True) = {result!r}, expected {expected!r}"

    def test_single_letter_initial_gets_period(self) -> None:
        """Single-letter middle initials should get a period."""
        result = smart_title_case("JOHN A SMITH")
        assert "A." in result

    def test_ii_suffix(self) -> None:
        """II suffix should remain uppercase."""
        result = smart_title_case("JAMES BROWN II")
        assert result == "James Brown II"

    def test_iv_suffix(self) -> None:
        """IV suffix should remain uppercase."""
        result = smart_title_case("JAMES BROWN IV")
        assert result == "James Brown IV"

    def test_sr_suffix(self) -> None:
        """Sr suffix should be preserved correctly."""
        result = smart_title_case("JAMES BROWN SR")
        assert result == "James Brown Sr"

    def test_double_hyphen_name(self) -> None:
        """Hyphenated names should have both parts title-cased."""
        result = smart_title_case("ANNE-MARIE JONES")
        assert result == "Anne-Marie Jones"

    def test_first_word_always_capitalized(self) -> None:
        """First word should always be capitalized even if it is a lowercase article."""
        result = smart_title_case("OF MICE AND MEN")
        assert result[0].isupper()
