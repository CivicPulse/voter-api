"""Unit tests for the normalize_registration_number utility."""

import pytest

from voter_api.lib.normalize import normalize_registration_number


class TestNormalizeRegistrationNumber:
    """Tests for leading-zero stripping."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("00013148", "13148"),
            ("13148", "13148"),
            ("10300400", "10300400"),
            ("00100200", "100200"),
            ("0", "0"),
            ("0000", "0"),
            ("1", "1"),
            ("007", "7"),
        ],
        ids=[
            "leading_zeros",
            "no_leading_zeros",
            "internal_zeros_unchanged",
            "only_leading_zeros_stripped",
            "single_zero",
            "all_zeros",
            "single_digit",
            "leading_zeros_short",
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        """Registration number is normalized correctly."""
        assert normalize_registration_number(raw) == expected
