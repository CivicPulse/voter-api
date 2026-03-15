"""Unit tests for the converter validation report.

Tests cover report generation including terminal rendering
and JSON output.
"""

import json
from pathlib import Path

from voter_api.lib.converter.report import ConversionReport


class TestConversionReport:
    """Tests for the ConversionReport class."""

    def test_empty_report(self) -> None:
        """New report has zero counts."""
        report = ConversionReport()
        assert report.files_processed == 0
        assert report.files_succeeded == 0
        assert report.files_failed == 0

    def test_add_success(self) -> None:
        """Adding a success increments counts correctly."""
        report = ConversionReport()
        report.add_success(Path("test.md"), record_count=3)

        assert report.files_processed == 1
        assert report.files_succeeded == 1
        assert report.files_failed == 0

    def test_add_failure(self) -> None:
        """Adding a failure increments counts and stores errors."""
        report = ConversionReport()
        report.add_failure(Path("bad.md"), errors=["Missing ID", "Invalid type"])

        assert report.files_processed == 1
        assert report.files_succeeded == 0
        assert report.files_failed == 1

    def test_add_warning(self) -> None:
        """Warnings are tracked without affecting success/failure counts."""
        report = ConversionReport()
        report.add_success(Path("test.md"), record_count=1)
        report.add_warning(Path("test.md"), "Minor issue")

        assert report.files_succeeded == 1
        assert report.files_failed == 0

    def test_render_terminal(self) -> None:
        """Terminal rendering produces a non-empty string."""
        report = ConversionReport()
        report.add_success(Path("good.md"), record_count=5)
        report.add_failure(Path("bad.md"), errors=["Error 1"])

        output = report.render_terminal()
        assert isinstance(output, str)
        assert len(output) > 0
        assert "good.md" in output
        assert "bad.md" in output

    def test_write_json(self, tmp_path: Path) -> None:
        """JSON report is written with correct structure."""
        report = ConversionReport()
        report.add_success(Path("good.md"), record_count=5)
        report.add_failure(Path("bad.md"), errors=["Error 1"])

        output = tmp_path / "report.json"
        report.write_json(output)

        assert output.exists()
        data = json.loads(output.read_text())
        assert data["total_files"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert "files" in data
        assert "errors" in data

    def test_mixed_operations(self) -> None:
        """Multiple successes and failures are tracked correctly."""
        report = ConversionReport()
        report.add_success(Path("a.md"), record_count=3)
        report.add_success(Path("b.md"), record_count=2)
        report.add_failure(Path("c.md"), errors=["Err"])
        report.add_warning(Path("a.md"), "Warning msg")

        assert report.files_processed == 3
        assert report.files_succeeded == 2
        assert report.files_failed == 1
