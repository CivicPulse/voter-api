"""Unit tests for the converter body/seat resolver.

Tests cover resolution of Body IDs to boundary_type values using
both the built-in statewide mapping and county reference file lookup.
"""

from pathlib import Path

from voter_api.lib.converter.resolver import (
    STATEWIDE_BODIES,
    load_county_references,
    parse_governing_bodies,
    resolve_body,
)

BIBB_REFERENCE_MD = """\
# Bibb County

## Metadata

| Field | Value |
|-------|-------|
| County | Bibb |
| State | Georgia |
| County Seat | Macon |

## Governing Bodies

| Body Name | Body ID | Boundary Type | Election Type | Seats |
|-----------|---------|---------------|---------------|-------|
| Board of Education | bibb-boe | school_board | nonpartisan | 8 |
| Sheriff | bibb-sheriff | county | nonpartisan | 1 |
| Superior Court | bibb-superior-court | judicial | nonpartisan | 4 |
| Probate Court | bibb-probate-court | county | nonpartisan | 1 |
"""


class TestStatewideResolution:
    """Tests for statewide/federal Body ID resolution."""

    def test_governor_resolves(self) -> None:
        """ga-governor resolves to None (statewide office, no boundary polygon)."""
        result = resolve_body("ga-governor", {})
        assert "ga-governor" in STATEWIDE_BODIES
        assert result is None

    def test_us_senate_resolves(self) -> None:
        """ga-us-senate resolves to us_senate."""
        result = resolve_body("ga-us-senate", {})
        assert result == "us_senate"

    def test_us_house_resolves(self) -> None:
        """ga-us-house resolves to congressional."""
        result = resolve_body("ga-us-house", {})
        assert result == "congressional"

    def test_state_senate_resolves(self) -> None:
        """ga-state-senate resolves to state_senate."""
        result = resolve_body("ga-state-senate", {})
        assert result == "state_senate"

    def test_state_house_resolves(self) -> None:
        """ga-state-house resolves to state_house."""
        result = resolve_body("ga-state-house", {})
        assert result == "state_house"

    def test_psc_resolves(self) -> None:
        """ga-psc resolves to psc."""
        result = resolve_body("ga-psc", {})
        assert result == "psc"

    def test_statewide_mapping_completeness(self) -> None:
        """All expected statewide body IDs are in the mapping."""
        expected = [
            "ga-governor",
            "ga-lt-governor",
            "ga-sos",
            "ga-ag",
            "ga-insurance",
            "ga-labor",
            "ga-school-superintendent",
            "ga-psc",
            "ga-us-senate",
            "ga-us-house",
            "ga-state-senate",
            "ga-state-house",
            "ga-supreme-court",
            "ga-court-of-appeals",
            "ga-superior-court",
        ]
        for body_id in expected:
            assert body_id in STATEWIDE_BODIES, f"Missing statewide body: {body_id}"


class TestCountyResolution:
    """Tests for county Body ID resolution via reference files."""

    def test_resolves_county_body(self) -> None:
        """County Body ID resolves via county reference lookup."""
        county_refs = {
            "bibb": {"bibb-boe": "school_board", "bibb-sheriff": "county"},
        }
        result = resolve_body("bibb-boe", county_refs)
        assert result == "school_board"

    def test_unknown_body_returns_none(self) -> None:
        """Unknown Body ID returns None."""
        county_refs = {
            "bibb": {"bibb-boe": "school_board"},
        }
        result = resolve_body("nonexistent-body", county_refs)
        assert result is None

    def test_statewide_takes_precedence(self) -> None:
        """Statewide mapping is checked before county references."""
        county_refs = {
            "ga": {"ga-governor": "wrong_type"},
        }
        result = resolve_body("ga-governor", county_refs)
        # Statewide mapping returns None (no boundary polygon), not the county override
        assert result is None
        assert result != "wrong_type"


class TestParseGoverningBodies:
    """Tests for parsing Governing Bodies tables from county reference files."""

    def test_parses_governing_bodies_table(self, tmp_path: Path) -> None:
        """Governing Bodies table is parsed into {body_id: boundary_type} mapping."""
        file = tmp_path / "bibb.md"
        file.write_text(BIBB_REFERENCE_MD)
        result = parse_governing_bodies(file)

        assert result["bibb-boe"] == "school_board"
        assert result["bibb-sheriff"] == "county"
        assert result["bibb-superior-court"] == "judicial"
        assert result["bibb-probate-court"] == "county"

    def test_missing_governing_bodies_returns_empty(self, tmp_path: Path) -> None:
        """File without Governing Bodies section returns empty dict."""
        file = tmp_path / "stub.md"
        file.write_text("# Some County\n\n## Metadata\n\n| Field | Value |\n")
        result = parse_governing_bodies(file)

        assert result == {}


class TestLoadCountyReferences:
    """Tests for loading all county reference files from a directory."""

    def test_loads_multiple_counties(self, tmp_path: Path) -> None:
        """Loads references from multiple county files."""
        (tmp_path / "bibb.md").write_text(BIBB_REFERENCE_MD)
        (tmp_path / "fulton.md").write_text(
            """\
# Fulton County

## Governing Bodies

| Body Name | Body ID | Boundary Type | Election Type | Seats |
|-----------|---------|---------------|---------------|-------|
| Board of Education | fulton-boe | school_board | nonpartisan | 7 |
"""
        )

        result = load_county_references(tmp_path)
        assert "bibb" in result
        assert "fulton" in result
        assert result["bibb"]["bibb-boe"] == "school_board"
        assert result["fulton"]["fulton-boe"] == "school_board"

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory returns empty dict."""
        result = load_county_references(tmp_path)
        assert result == {}
