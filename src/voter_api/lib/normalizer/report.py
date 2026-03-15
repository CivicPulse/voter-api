"""Normalization validation report generator.

Tracks file processing results and generates both terminal-readable
summaries and machine-readable JSON reports. Follows the same pattern
as lib/converter/report.py for consistency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class FileResult:
    """Result for a single processed file.

    Attributes:
        file_path: Path to the processed file.
        status: "success" or "failure".
        changes_count: Number of field changes made.
        errors: List of error messages if normalization failed.
        warnings: List of warning messages.
    """

    file_path: Path
    status: str  # "success" or "failure"
    changes_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class NormalizationReport:
    """Tracks normalization results and generates reports.

    Provides methods to record successes, failures, warnings, UUID
    generation events, and file rename events. Can render results as
    terminal output or write a machine-readable JSON file.
    """

    def __init__(self) -> None:
        """Initialize an empty report."""
        self._files: list[FileResult] = []
        self._warnings: list[tuple[Any, str]] = []
        self._uuids_generated: int = 0
        self._files_renamed: int = 0

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

    @property
    def uuids_generated(self) -> int:
        """Total number of UUIDs generated during normalization."""
        return self._uuids_generated

    @property
    def files_renamed(self) -> int:
        """Total number of files renamed during normalization."""
        return self._files_renamed

    def add_success(self, file_path: Path, changes_count: int) -> None:
        """Record a successful file normalization.

        Args:
            file_path: Path to the normalized file.
            changes_count: Number of field changes made to the file.
        """
        self._files.append(
            FileResult(
                file_path=file_path,
                status="success",
                changes_count=changes_count,
            )
        )

    def add_failure(self, file_path: Path, errors: list[str]) -> None:
        """Record a failed file normalization.

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

        Warnings do not affect success/failure status.

        Args:
            file_path: Path to the file with a warning.
            message: Warning message.
        """
        self._warnings.append((file_path, message))
        # Also add to the file result if it exists
        for f in self._files:
            if f.file_path == file_path:
                f.warnings.append(message)
                break

    def add_uuid_generated(self, file_path: Path) -> None:
        """Record that a UUID was generated for a file.

        Args:
            file_path: Path to the file for which a UUID was generated.
        """
        self._uuids_generated += 1

    def add_file_renamed(self, old_path: Path, new_path: Path) -> None:
        """Record that a file was renamed during normalization.

        Args:
            old_path: Original file path.
            new_path: New file path after renaming.
        """
        self._files_renamed += 1

    def render_terminal(self) -> str:
        """Render a human-readable summary table.

        Returns:
            Formatted string with file results table and totals.
        """
        lines: list[str] = []
        lines.append("")
        lines.append("Normalization Report")
        lines.append("=" * 60)
        lines.append(
            f"  Total: {self.files_processed}"
            f"  Succeeded: {self.files_succeeded}"
            f"  Failed: {self.files_failed}"
            f"  UUIDs Generated: {self.uuids_generated}"
            f"  Renamed: {self.files_renamed}"
        )
        lines.append("-" * 60)
        lines.append(f"{'File':<40} {'Status':<10} {'Changes':<8}")
        lines.append("-" * 60)

        for f in self._files:
            name = str(f.file_path)
            if len(name) > 38:
                name = "..." + name[-35:]
            status = f.status.upper()
            changes = str(f.changes_count) if f.status == "success" else "-"
            lines.append(f"{name:<40} {status:<10} {changes:<8}")

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

        The JSON output includes aggregate counts, per-file details,
        and warnings.

        Args:
            output_path: Path to write the JSON report.
        """
        data: dict[str, Any] = {
            "total_files": self.files_processed,
            "succeeded": self.files_succeeded,
            "failed": self.files_failed,
            "uuids_generated": self.uuids_generated,
            "files_renamed": self.files_renamed,
            "files": [
                {
                    "path": str(f.file_path),
                    "status": f.status,
                    "changes_count": f.changes_count,
                    "errors": f.errors,
                    "warnings": f.warnings,
                }
                for f in self._files
            ],
            "warnings": [{"file": str(path), "message": msg} for path, msg in self._warnings],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2)
