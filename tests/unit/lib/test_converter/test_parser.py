"""Unit tests for the converter markdown parser.

Tests cover parsing of all three file types: election overview,
single-contest, and multi-contest (county) files. Uses fixture
markdown strings matching the format specifications.
"""

from pathlib import Path

from voter_api.lib.converter.parser import parse_markdown
from voter_api.lib.converter.types import FileType

# -- Fixtures: markdown content strings --

OVERVIEW_MD = """\
# May 19, 2026 \u2014 General and Primary Election

## Metadata

| Field | Value |
|-------|-------|
| ID | 550e8400-e29b-41d4-a716-446655440000 |
| Format Version | 1 |
| Name (SOS) | May 19, 2026 General Primary/Nonpartisan/SPLOST |
| Date | 2026-05-19 |
| Type | general_primary |
| Stage | election |

## Calendar

| Field | Date | Source |
|-------|------|--------|
| Registration Deadline | 2026-04-21 | SOS Election Calendar |
| Early Voting Start | 2026-04-27 | SOS Election Calendar |
| Early Voting End | 2026-05-15 | SOS Election Calendar |
| Election Day | 2026-05-19 | SOS Election Calendar |
"""

SINGLE_CONTEST_MD = """\
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

## Republican Primary

**Contest Name (SOS):** Governor (R)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Brian Kemp | Qualified | Yes | Governor | 03/07/2026 |
| David Perdue | Qualified | No | Business Executive | 03/08/2026 |

## Democrat Primary

**Contest Name (SOS):** Governor (D)

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Stacey Abrams | Qualified | No | Attorney | 03/07/2026 |
"""

MULTI_CONTEST_MD = """\
# Bibb County \u2014 Local Elections

## Metadata

| Field | Value |
|-------|-------|
| ID | 770e8400-e29b-41d4-a716-446655440002 |
| Format Version | 1 |
| Election | [May 19, 2026 General Primary](../2026-05-19-general-primary.md) |
| Type | general_primary |
| Contests | 2 |
| Candidates | 4 |

## Contests

### Board of Education At Large-Post 7

**Body:** bibb-boe | **Seat:** post-7

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| John Smith | Qualified | No | Educator | 03/07/2026 |
| Jane Doe | Qualified | Yes | Teacher | 03/08/2026 |

### Sheriff

**Body:** bibb-sheriff | **Seat:** sole

| Candidate | Status | Incumbent | Occupation | Qualified Date |
|-----------|--------|-----------|------------|----------------|
| Bob Jones | Qualified | Yes | Sheriff | 03/07/2026 |
| Alice Brown | Qualified | No | Police Officer | 03/09/2026 |
"""

MISSING_ID_MD = """\
# Some Election

## Metadata

| Field | Value |
|-------|-------|
| Format Version | 1 |
| Date | 2026-05-19 |
| Type | general_primary |
"""

INVALID_UUID_MD = """\
# Some Election

## Metadata

| Field | Value |
|-------|-------|
| ID | not-a-valid-uuid |
| Format Version | 1 |
| Date | 2026-05-19 |
| Type | general_primary |
"""

EMPTY_ID_MD = """\
# Some Election

## Metadata

| Field | Value |
|-------|-------|
| ID | |
| Format Version | 1 |
| Date | 2026-05-19 |
| Type | general_primary |
"""

SEVEN_COLUMN_MD = """\
# Some Contest

## Metadata

| Field | Value |
|-------|-------|
| ID | 880e8400-e29b-41d4-a716-446655440003 |
| Format Version | 1 |
| Election | [Election](overview.md) |
| Type | general_primary |
| Stage | election |
| Body | ga-governor |
| Seat | sole |
| Name (SOS) | Governor |

## Candidates

| Candidate | Party | Filing Status | Ballot Order | Incumbent | Email | Website |
|-----------|-------|---------------|--------------|-----------|-------|---------|
| John Doe | Republican | Qualified | 1 | Yes | john@example.com | example.com |
"""


class TestParseOverview:
    """Tests for parsing election overview markdown files."""

    def test_parses_overview_metadata(self, tmp_path: Path) -> None:
        """Overview file metadata table is extracted correctly."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_MD)
        result = parse_markdown(file)

        assert result.file_type == FileType.OVERVIEW
        assert result.metadata["ID"] == "550e8400-e29b-41d4-a716-446655440000"
        assert result.metadata["Format Version"] == "1"
        assert result.metadata["Name (SOS)"] == "May 19, 2026 General Primary/Nonpartisan/SPLOST"
        assert result.metadata["Date"] == "2026-05-19"
        assert result.metadata["Type"] == "general_primary"
        assert result.metadata["Stage"] == "election"

    def test_parses_calendar_table(self, tmp_path: Path) -> None:
        """Calendar table dates are extracted from overview files."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_MD)
        result = parse_markdown(file)

        assert result.calendar["Registration Deadline"] == "2026-04-21"
        assert result.calendar["Early Voting Start"] == "2026-04-27"
        assert result.calendar["Election Day"] == "2026-05-19"

    def test_overview_has_no_contests(self, tmp_path: Path) -> None:
        """Overview files should not have contest data."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_MD)
        result = parse_markdown(file)

        assert result.contests == []

    def test_overview_heading_extracted(self, tmp_path: Path) -> None:
        """The H1 heading is captured from the overview file."""
        file = tmp_path / "2026-05-19-general-primary.md"
        file.write_text(OVERVIEW_MD)
        result = parse_markdown(file)

        assert "General and Primary Election" in result.heading


class TestParseSingleContest:
    """Tests for parsing single-contest markdown files."""

    def test_parses_single_contest_metadata(self, tmp_path: Path) -> None:
        """Single-contest file metadata is extracted correctly."""
        file = tmp_path / "2026-05-19-governor.md"
        file.write_text(SINGLE_CONTEST_MD)
        result = parse_markdown(file)

        assert result.file_type == FileType.SINGLE_CONTEST
        assert result.metadata["ID"] == "660e8400-e29b-41d4-a716-446655440001"
        assert result.metadata["Body"] == "ga-governor"
        assert result.metadata["Seat"] == "sole"

    def test_extracts_candidate_tables(self, tmp_path: Path) -> None:
        """Candidate tables from party sections are extracted."""
        file = tmp_path / "2026-05-19-governor.md"
        file.write_text(SINGLE_CONTEST_MD)
        result = parse_markdown(file)

        # Single-contest with party sections creates contest entries
        assert len(result.contests) >= 1
        # Should have candidates from both party tables
        all_candidates = []
        for contest in result.contests:
            all_candidates.extend(contest.candidates)
        assert len(all_candidates) == 3

    def test_extracts_candidate_fields(self, tmp_path: Path) -> None:
        """Individual candidate fields are correctly extracted from table rows."""
        file = tmp_path / "2026-05-19-governor.md"
        file.write_text(SINGLE_CONTEST_MD)
        result = parse_markdown(file)

        all_candidates = []
        for contest in result.contests:
            all_candidates.extend(contest.candidates)

        kemp = next(c for c in all_candidates if "Kemp" in c.get("Candidate", ""))
        assert kemp["Status"] == "Qualified"
        assert kemp["Incumbent"] == "Yes"
        assert kemp["Occupation"] == "Governor"


class TestParseMultiContest:
    """Tests for parsing multi-contest county markdown files."""

    def test_parses_multi_contest_metadata(self, tmp_path: Path) -> None:
        """Multi-contest file metadata is extracted correctly."""
        file = tmp_path / "2026-05-19-bibb.md"
        file.write_text(MULTI_CONTEST_MD)
        result = parse_markdown(file)

        assert result.file_type == FileType.MULTI_CONTEST
        assert result.metadata["ID"] == "770e8400-e29b-41d4-a716-446655440002"

    def test_extracts_contest_sections(self, tmp_path: Path) -> None:
        """Individual contest sections are split by ### headings."""
        file = tmp_path / "2026-05-19-bibb.md"
        file.write_text(MULTI_CONTEST_MD)
        result = parse_markdown(file)

        assert len(result.contests) == 2
        assert result.contests[0].heading == "Board of Education At Large-Post 7"
        assert result.contests[1].heading == "Sheriff"

    def test_extracts_body_seat_from_contests(self, tmp_path: Path) -> None:
        """Body and Seat are extracted from per-contest metadata lines."""
        file = tmp_path / "2026-05-19-bibb.md"
        file.write_text(MULTI_CONTEST_MD)
        result = parse_markdown(file)

        assert result.contests[0].body_id == "bibb-boe"
        assert result.contests[0].seat_id == "post-7"
        assert result.contests[1].body_id == "bibb-sheriff"
        assert result.contests[1].seat_id == "sole"

    def test_extracts_candidates_per_contest(self, tmp_path: Path) -> None:
        """Candidates are associated with the correct contest section."""
        file = tmp_path / "2026-05-19-bibb.md"
        file.write_text(MULTI_CONTEST_MD)
        result = parse_markdown(file)

        assert len(result.contests[0].candidates) == 2
        assert len(result.contests[1].candidates) == 2


class TestUUIDValidation:
    """Tests for UUID validation during parsing."""

    def test_missing_id_produces_error(self, tmp_path: Path) -> None:
        """Missing ID field in metadata produces a validation error."""
        file = tmp_path / "missing-id.md"
        file.write_text(MISSING_ID_MD)
        result = parse_markdown(file)

        assert len(result.errors) > 0
        assert any("UUID_MISSING" in e or "ID" in e for e in result.errors)

    def test_invalid_uuid_produces_error(self, tmp_path: Path) -> None:
        """Invalid UUID value produces a validation error."""
        file = tmp_path / "invalid-uuid.md"
        file.write_text(INVALID_UUID_MD)
        result = parse_markdown(file)

        assert len(result.errors) > 0
        assert any("UUID_INVALID" in e or "Invalid" in e for e in result.errors)

    def test_empty_id_produces_error(self, tmp_path: Path) -> None:
        """Empty ID value produces a validation error."""
        file = tmp_path / "empty-id.md"
        file.write_text(EMPTY_ID_MD)
        result = parse_markdown(file)

        assert len(result.errors) > 0
        assert any("UUID_MISSING" in e or "ID" in e for e in result.errors)


class TestLegacyFormat:
    """Tests for handling legacy 7-column candidate tables."""

    def test_handles_seven_column_table(self, tmp_path: Path) -> None:
        """Seven-column candidate tables (legacy) are parsed correctly."""
        file = tmp_path / "legacy.md"
        file.write_text(SEVEN_COLUMN_MD)
        result = parse_markdown(file)

        all_candidates = []
        for contest in result.contests:
            all_candidates.extend(contest.candidates)
        assert len(all_candidates) == 1
        assert "Doe" in all_candidates[0].get("Candidate", "")
