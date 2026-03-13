"""Tests for the HTML election calendar preprocessor."""

from pathlib import Path

from voter_api.lib.election_calendar.html_preprocessor import preprocess_html_calendar
from voter_api.lib.election_calendar.parser import parse_calendar_jsonl


class TestPreprocessHtmlCalendar:
    """Tests for preprocess_html_calendar."""

    def _create_test_html(self, path: Path) -> Path:
        """Create a minimal HTML file with an election calendar table.

        Args:
            path: Directory to write the file in.

        Returns:
            Path to the created HTML file.
        """
        html = """<!DOCTYPE html>
<html>
<body>
<table>
  <tr>
    <th>ELECTION</th>
    <th>ELECTION DATE</th>
    <th>ADVANCE VOTING DATES</th>
    <th>REGISTRATION DEADLINE</th>
  </tr>
  <tr>
    <td>General Primary Election</td>
    <td>05/19/2026</td>
    <td>04/27/26 - 05/15/26</td>
    <td>04/20/2026</td>
  </tr>
  <tr>
    <td>General Election</td>
    <td>11/03/2026</td>
    <td>10/13/26 - 10/30/26</td>
    <td>10/05/2026</td>
  </tr>
</table>
</body>
</html>"""
        html_path = path / "calendar.html"
        html_path.write_text(html)
        return html_path

    def test_produces_valid_jsonl(self, tmp_path: Path) -> None:
        """HTML table produces parseable JSONL output."""
        html_path = self._create_test_html(tmp_path)
        output_path = tmp_path / "output.jsonl"

        count = preprocess_html_calendar(html_path, output_path)

        assert count == 2
        entries = parse_calendar_jsonl(output_path)
        assert len(entries) == 2

    def test_election_names_extracted(self, tmp_path: Path) -> None:
        """Election names are correctly extracted from HTML."""
        html_path = self._create_test_html(tmp_path)
        output_path = tmp_path / "output.jsonl"

        preprocess_html_calendar(html_path, output_path)
        entries = parse_calendar_jsonl(output_path)

        names = [e.election_name for e in entries]
        assert "General Primary Election" in names
        assert "General Election" in names

    def test_dates_parsed(self, tmp_path: Path) -> None:
        """Dates are correctly parsed from HTML table cells."""
        html_path = self._create_test_html(tmp_path)
        output_path = tmp_path / "output.jsonl"

        preprocess_html_calendar(html_path, output_path)
        entries = parse_calendar_jsonl(output_path)

        primary = next(e for e in entries if "Primary" in e.election_name)
        assert str(primary.election_date) == "2026-05-19"
        assert str(primary.registration_deadline) == "2026-04-20"
        assert str(primary.early_voting_start) == "2026-04-27"
        assert str(primary.early_voting_end) == "2026-05-15"

    def test_no_table_returns_zero(self, tmp_path: Path) -> None:
        """HTML without tables returns 0 entries."""
        html_path = tmp_path / "empty.html"
        html_path.write_text("<html><body><p>No tables here</p></body></html>")
        output_path = tmp_path / "output.jsonl"

        count = preprocess_html_calendar(html_path, output_path)

        assert count == 0

    def test_table_without_header_skipped(self, tmp_path: Path) -> None:
        """Table without election header row is skipped."""
        html = """<html><body><table>
        <tr><td>Foo</td><td>Bar</td></tr>
        <tr><td>Baz</td><td>Qux</td></tr>
        </table></body></html>"""
        html_path = tmp_path / "no_header.html"
        html_path.write_text(html)
        output_path = tmp_path / "output.jsonl"

        count = preprocess_html_calendar(html_path, output_path)

        assert count == 0

    def test_multiline_election_name(self, tmp_path: Path) -> None:
        """Election name spanning multiple lines is joined."""
        html = """<html><body><table>
        <tr><th>ELECTION</th><th>ELECTION DATE</th></tr>
        <tr><td>General Primary<br/>Election/Nonpartisan</td><td>05/19/2026</td></tr>
        </table></body></html>"""
        html_path = tmp_path / "multiline.html"
        html_path.write_text(html)
        output_path = tmp_path / "output.jsonl"

        preprocess_html_calendar(html_path, output_path)
        entries = parse_calendar_jsonl(output_path)

        assert len(entries) == 1
        assert "Primary" in entries[0].election_name
