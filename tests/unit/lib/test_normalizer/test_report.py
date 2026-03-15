"""Unit tests for NormalizationReport."""

from __future__ import annotations

import json
from pathlib import Path

from voter_api.lib.normalizer.report import NormalizationReport


class TestNormalizationReport:
    """Tests for the NormalizationReport class."""

    def test_initial_state(self) -> None:
        """Report starts with zero counts."""
        report = NormalizationReport()
        assert report.files_processed == 0
        assert report.files_succeeded == 0
        assert report.files_failed == 0
        assert report.uuids_generated == 0
        assert report.files_renamed == 0

    def test_add_success_increments_processed_and_succeeded(self) -> None:
        """add_success increments files_processed and files_succeeded."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 3)
        assert report.files_processed == 1
        assert report.files_succeeded == 1
        assert report.files_failed == 0

    def test_add_failure_increments_processed_and_failed(self) -> None:
        """add_failure increments files_processed and files_failed."""
        report = NormalizationReport()
        report.add_failure(Path("test.md"), ["Error 1", "Error 2"])
        assert report.files_processed == 1
        assert report.files_succeeded == 0
        assert report.files_failed == 1

    def test_add_warning_adds_to_warnings_list(self) -> None:
        """add_warning records a warning message."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 0)
        report.add_warning(Path("test.md"), "Some warning")
        # Warning should be accessible in the terminal output
        output = report.render_terminal()
        assert "Some warning" in output

    def test_add_uuid_generated_increments_counter(self) -> None:
        """add_uuid_generated increments the uuids_generated count."""
        report = NormalizationReport()
        report.add_uuid_generated(Path("test.md"))
        assert report.uuids_generated == 1
        report.add_uuid_generated(Path("other.md"))
        assert report.uuids_generated == 2

    def test_add_file_renamed_increments_counter(self) -> None:
        """add_file_renamed increments the files_renamed count."""
        report = NormalizationReport()
        report.add_file_renamed(Path("old.md"), Path("new.md"))
        assert report.files_renamed == 1
        report.add_file_renamed(Path("old2.md"), Path("new2.md"))
        assert report.files_renamed == 2

    def test_files_processed_is_total_of_succeeded_and_failed(self) -> None:
        """files_processed equals sum of succeeded and failed."""
        report = NormalizationReport()
        report.add_success(Path("a.md"), 1)
        report.add_success(Path("b.md"), 2)
        report.add_failure(Path("c.md"), ["err"])
        assert report.files_processed == 3
        assert report.files_succeeded == 2
        assert report.files_failed == 1

    def test_render_terminal_contains_totals(self) -> None:
        """render_terminal output contains key totals."""
        report = NormalizationReport()
        report.add_success(Path("file1.md"), 5)
        report.add_failure(Path("file2.md"), ["parse error"])
        output = report.render_terminal()
        assert "Total:" in output or "total" in output.lower()
        assert "2" in output  # 2 files processed

    def test_render_terminal_contains_file_names(self) -> None:
        """render_terminal output includes file names."""
        report = NormalizationReport()
        report.add_success(Path("candidates/john-smith.md"), 3)
        output = report.render_terminal()
        assert "john-smith" in output or "SUCCESS" in output

    def test_render_terminal_shows_success_status(self) -> None:
        """render_terminal shows SUCCESS for successful files."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 0)
        output = report.render_terminal()
        assert "SUCCESS" in output

    def test_render_terminal_shows_failure_status(self) -> None:
        """render_terminal shows FAILURE for failed files."""
        report = NormalizationReport()
        report.add_failure(Path("test.md"), ["error message"])
        output = report.render_terminal()
        assert "FAILURE" in output

    def test_render_terminal_shows_errors(self) -> None:
        """render_terminal includes error messages."""
        report = NormalizationReport()
        report.add_failure(Path("test.md"), ["specific error text"])
        output = report.render_terminal()
        assert "specific error text" in output

    def test_write_json_creates_file(self, tmp_path: Path) -> None:
        """write_json creates a JSON file at the specified path."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 2)
        output_path = tmp_path / "report.json"
        report.write_json(output_path)
        assert output_path.exists()

    def test_write_json_includes_totals(self, tmp_path: Path) -> None:
        """write_json output includes aggregate count fields."""
        report = NormalizationReport()
        report.add_success(Path("a.md"), 1)
        report.add_failure(Path("b.md"), ["err"])
        report.add_uuid_generated(Path("a.md"))
        report.add_file_renamed(Path("old.md"), Path("new.md"))
        output_path = tmp_path / "report.json"
        report.write_json(output_path)

        data = json.loads(output_path.read_text())
        assert data["total_files"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert data["uuids_generated"] == 1
        assert data["files_renamed"] == 1

    def test_write_json_includes_per_file_details(self, tmp_path: Path) -> None:
        """write_json output includes per-file details."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 5)
        output_path = tmp_path / "report.json"
        report.write_json(output_path)

        data = json.loads(output_path.read_text())
        assert "files" in data
        assert len(data["files"]) == 1
        assert data["files"][0]["status"] == "success"
        assert data["files"][0]["changes_count"] == 5

    def test_write_json_includes_warnings(self, tmp_path: Path) -> None:
        """write_json output includes warnings list."""
        report = NormalizationReport()
        report.add_success(Path("test.md"), 0)
        report.add_warning(Path("test.md"), "warning text")
        output_path = tmp_path / "report.json"
        report.write_json(output_path)

        data = json.loads(output_path.read_text())
        assert "warnings" in data
        assert len(data["warnings"]) >= 1

    def test_write_json_creates_parent_dirs(self, tmp_path: Path) -> None:
        """write_json creates parent directories as needed."""
        report = NormalizationReport()
        output_path = tmp_path / "nested" / "dir" / "report.json"
        report.write_json(output_path)
        assert output_path.exists()
