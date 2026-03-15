"""Conversion validation report generator.

Tracks file processing results and generates both terminal-readable
summaries and machine-readable JSON reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class FileResult:
    """Result for a single processed file."""

    file_path: Path
    status: str  # "success" or "failure"
    record_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ConversionReport:
    """Tracks conversion results and generates reports.

    Provides methods to record successes, failures, and warnings,
    and to render the results as terminal output or JSON.
    """

    def __init__(self) -> None:
        """Initialize an empty report."""
        self._files: list[FileResult] = []
        self._warnings: list[tuple[Path, str]] = []

    @property
    def files_processed(self) -> int:
        """Total number of files processed."""
        return len(self._files)

    @property
    def files_succeeded(self) -> int:
        """Number of files that succeeded."""
        return sum(1 for f in self._files if f.status == "success")

    @property
    def files_failed(self) -> int:
        """Number of files that failed."""
        return sum(1 for f in self._files if f.status == "failure")

    def add_success(self, file_path: Path, record_count: int) -> None:
        """Record a successful file conversion.

        Args:
            file_path: Path to the converted file.
            record_count: Number of JSONL records produced.
        """
        self._files.append(
            FileResult(
                file_path=file_path,
                status="success",
                record_count=record_count,
            )
        )

    def add_failure(self, file_path: Path, errors: list[str]) -> None:
        """Record a failed file conversion.

        Args:
            file_path: Path to the file that failed.
            errors: List of error messages describing the failures.
        """
        self._files.append(
            FileResult(
                file_path=file_path,
                status="failure",
                errors=errors,
            )
        )

    def add_warning(self, file_path: Path, message: str) -> None:
        """Record a warning for a file.

        Warnings don't affect success/failure status.

        Args:
            file_path: Path to the file with a warning.
            message: Warning message.
        """
        self._warnings.append((file_path, message))
        # Also add to file result if it exists
        for f in self._files:
            if f.file_path == file_path:
                f.warnings.append(message)
                break

    def render_terminal(self) -> str:
        """Render a human-readable summary table.

        Returns:
            Formatted string with file results table.
        """
        lines: list[str] = []
        lines.append("")
        lines.append("Conversion Report")
        lines.append("=" * 60)
        lines.append(f"  Total: {self.files_processed}  Succeeded: {self.files_succeeded}  Failed: {self.files_failed}")
        lines.append("-" * 60)
        lines.append(f"{'File':<40} {'Status':<10} {'Records':<8}")
        lines.append("-" * 60)

        for f in self._files:
            name = str(f.file_path)
            if len(name) > 38:
                name = "..." + name[-35:]
            status = f.status.upper()
            records = str(f.record_count) if f.status == "success" else "-"
            lines.append(f"{name:<40} {status:<10} {records:<8}")

            for error in f.errors:
                lines.append(f"  ERROR: {error}")

        if self._warnings:
            lines.append("")
            lines.append("Warnings:")
            for path, msg in self._warnings:
                lines.append(f"  {path}: {msg}")

        lines.append("=" * 60)
        lines.append("")

        return "\n".join(lines)

    def write_json(self, output_path: Path) -> None:
        """Write a machine-readable JSON report file.

        Args:
            output_path: Path to write the JSON report.
        """
        data: dict[str, Any] = {
            "total_files": self.files_processed,
            "succeeded": self.files_succeeded,
            "failed": self.files_failed,
            "files": [
                {
                    "path": str(f.file_path),
                    "status": f.status,
                    "record_count": f.record_count,
                    "errors": f.errors,
                    "warnings": f.warnings,
                }
                for f in self._files
            ],
            "errors": [{"file": str(f.file_path), "messages": f.errors} for f in self._files if f.errors],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2)
