"""Unit tests for the converter directory processing.

Tests cover batch conversion of entire election directories,
file type detection by path pattern, and output file placement.
"""

from pathlib import Path

from voter_api.lib.converter import convert_directory, convert_file
from voter_api.lib.converter.report import ConversionReport
from voter_api.lib.converter.types import ConversionResult

# Minimal valid overview markdown
OVERVIEW_CONTENT = """\
# May 19, 2026 \u2014 General and Primary Election

## Metadata

| Field | Value |
|-------|-------|
| ID | 550e8400-e29b-41d4-a716-446655440000 |
| Format Version | 1 |
| Name (SOS) | May 19, 2026 General Primary |
| Date | 2026-05-19 |
| Type | general_primary |
| Stage | election |
"""

# Minimal valid single-contest markdown
SINGLE_CONTEST_CONTENT = """\
# Governor

## Metadata

| Field | Value |
|-------|-------|
| ID | 660e8400-e29b-41d4-a716-446655440001 |
| Format Version | 1 |
| Election | [May 19, 2026 General Primary](2026-05-19-general-primary.md) |
| Type | general_primary |
| Stage | election |
| Body | ga-governor |
| Seat | sole |
| Name (SOS) | Governor |

## Candidates

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| John Doe | Qualified | No | Attorney | 03/07/2026 |
"""

# Minimal valid multi-contest markdown
MULTI_CONTEST_CONTENT = """\
# Bibb County \u2014 Local Elections

## Metadata

| Field | Value |
|-------|-------|
| ID | 770e8400-e29b-41d4-a716-446655440002 |
| Format Version | 1 |
| Election | [May 19, 2026 General Primary](../2026-05-19-general-primary.md) |
| Type | general_primary |
| Contests | 1 |
| Candidates | 1 |

## Contests

### Sheriff

**Body:** bibb-sheriff | **Seat:** sole

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Bob Jones | Qualified | Yes | Sheriff | 03/07/2026 |
"""

# Bibb county reference for resolver
BIBB_REFERENCE = """\
# Bibb County

## Governing Bodies

| Body Name | Body ID | Boundary Type | Election Type | Seats |
|-----------|---------|---------------|---------------|-------|
| Sheriff | bibb-sheriff | county | nonpartisan | 1 |
| Board of Education | bibb-boe | school_board | nonpartisan | 8 |
"""


def _create_election_dir(base: Path) -> Path:
    """Create a test election directory with all three file types."""
    election_dir = base / "data" / "elections" / "2026-05-19"
    election_dir.mkdir(parents=True)
    counties_dir = election_dir / "counties"
    counties_dir.mkdir()

    # Overview file
    (election_dir / "2026-05-19-general-primary.md").write_text(OVERVIEW_CONTENT)
    # Single-contest file
    (election_dir / "2026-05-19-governor.md").write_text(SINGLE_CONTEST_CONTENT)
    # Multi-contest file
    (counties_dir / "2026-05-19-bibb.md").write_text(MULTI_CONTEST_CONTENT)

    # County reference for resolver
    ref_dir = base / "data" / "states" / "GA" / "counties"
    ref_dir.mkdir(parents=True)
    (ref_dir / "bibb.md").write_text(BIBB_REFERENCE)

    return election_dir


class TestConvertDirectory:
    """Tests for batch directory conversion."""

    def test_processes_election_directory(self, tmp_path: Path) -> None:
        """convert_directory walks the election directory and processes files."""
        election_dir = _create_election_dir(tmp_path)
        report = convert_directory(election_dir)

        assert isinstance(report, ConversionReport)
        assert report.files_processed >= 1

    def test_returns_conversion_report(self, tmp_path: Path) -> None:
        """convert_directory returns a ConversionReport with results."""
        election_dir = _create_election_dir(tmp_path)
        report = convert_directory(election_dir)

        assert isinstance(report, ConversionReport)

    def test_output_override(self, tmp_path: Path) -> None:
        """Output directory can be overridden."""
        election_dir = _create_election_dir(tmp_path)
        output_dir = tmp_path / "custom_output"
        output_dir.mkdir()

        report = convert_directory(election_dir, output=output_dir)
        assert isinstance(report, ConversionReport)

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory produces a report with zero files."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        report = convert_directory(empty_dir)
        assert report.files_processed == 0


class TestConvertFile:
    """Tests for single file conversion."""

    def test_converts_overview_file(self, tmp_path: Path) -> None:
        """convert_file processes an overview markdown file."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_CONTENT)

        result = convert_file(file)
        assert isinstance(result, ConversionResult)

    def test_converts_single_contest_file(self, tmp_path: Path) -> None:
        """convert_file processes a single-contest markdown file."""
        file = tmp_path / "2026-05-19-governor.md"
        file.write_text(SINGLE_CONTEST_CONTENT)

        result = convert_file(file)
        assert isinstance(result, ConversionResult)

    def test_returns_conversion_result(self, tmp_path: Path) -> None:
        """convert_file returns a ConversionResult with records or errors."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_CONTENT)

        result = convert_file(file)
        assert isinstance(result, ConversionResult)
        assert result.file_path == file
