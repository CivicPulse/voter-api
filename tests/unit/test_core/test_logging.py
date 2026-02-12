"""Unit tests for logging configuration."""

from voter_api.core.logging import setup_logging


class TestLogging:
    """Tests for Loguru logging setup."""

    def test_setup_logging_does_not_raise(self) -> None:
        """setup_logging with valid log level does not raise."""
        setup_logging("DEBUG")
        setup_logging("INFO")
        setup_logging("WARNING")

    def test_setup_logging_case_insensitive(self) -> None:
        """setup_logging accepts case-insensitive log levels."""
        setup_logging("info")
        setup_logging("debug")
