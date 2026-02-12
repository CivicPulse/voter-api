"""Tests for the county-to-district CSV loader."""

import textwrap
from pathlib import Path

import pytest

from voter_api.lib.boundary_loader.csv_loader import (
    CountyDistrictRecord,
    _parse_district_numbers,
    parse_county_districts_csv,
)


class TestParseDistrictNumbers:
    """Tests for _parse_district_numbers helper."""

    def test_single_number(self) -> None:
        assert _parse_district_numbers("1") == ["001"]

    def test_multiple_comma_separated(self) -> None:
        assert _parse_district_numbers("2, 8") == ["002", "008"]

    def test_many_numbers(self) -> None:
        assert _parse_district_numbers("142, 143, 144, 145, 149") == [
            "142",
            "143",
            "144",
            "145",
            "149",
        ]

    def test_trailing_comma(self) -> None:
        """Multi-row counties in the CSV have trailing commas."""
        assert _parse_district_numbers("25, 47, 48, 49,") == ["025", "047", "048", "049"]

    def test_empty_string(self) -> None:
        assert _parse_district_numbers("") == []

    def test_whitespace_only(self) -> None:
        assert _parse_district_numbers("   ") == []

    def test_strips_whitespace(self) -> None:
        assert _parse_district_numbers(" 1 , 2 , 3 ") == ["001", "002", "003"]

    def test_zero_pads_to_three_digits(self) -> None:
        """District numbers are zero-padded to match shapefile DISTRICT column format."""
        assert _parse_district_numbers("2") == ["002"]
        assert _parse_district_numbers("18") == ["018"]
        assert _parse_district_numbers("142") == ["142"]


class TestParseCountyDistrictsCsv:
    """Tests for parse_county_districts_csv."""

    def test_basic_parsing(self, tmp_path: Path) -> None:
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts,House Districts
            APPLING,1,19,"157, 178"
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        records = parse_county_districts_csv(csv_file)

        assert len(records) == 4
        assert CountyDistrictRecord("APPLING", "congressional", "001") in records
        assert CountyDistrictRecord("APPLING", "state_senate", "019") in records
        assert CountyDistrictRecord("APPLING", "state_house", "157") in records
        assert CountyDistrictRecord("APPLING", "state_house", "178") in records

    def test_multi_row_county_deduplication(self, tmp_path: Path) -> None:
        """Counties with split rows (like COBB) should merge and deduplicate."""
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts,House Districts
            COBB,"6, 11, 14","28, 32, 33","19, 22, 34"
            COBB,"6, 11, 14","28, 32, 33","41, 42, 43"
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        records = parse_county_districts_csv(csv_file)

        cobb_congressional = [r for r in records if r.boundary_type == "congressional"]
        cobb_house = [r for r in records if r.boundary_type == "state_house"]

        # Congressional should be deduplicated (same values in both rows)
        assert len(cobb_congressional) == 3

        # House should be merged (different values across rows)
        assert len(cobb_house) == 6
        house_ids = {r.district_identifier for r in cobb_house}
        assert house_ids == {"019", "022", "034", "041", "042", "043"}

    def test_county_name_uppercased(self, tmp_path: Path) -> None:
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts,House Districts
            bibb,2,18,142
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        records = parse_county_districts_csv(csv_file)

        assert all(r.county_name == "BIBB" for r in records)

    def test_missing_column_raises(self, tmp_path: Path) -> None:
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts
            BIBB,2,18
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        with pytest.raises(ValueError, match="missing expected columns"):
            parse_county_districts_csv(csv_file)

    def test_empty_header_raises(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        with pytest.raises(ValueError, match="no header row"):
            parse_county_districts_csv(csv_file)

    def test_results_sorted(self, tmp_path: Path) -> None:
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts,House Districts
            BIBB,2,18,142
            APPLING,1,19,157
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        records = parse_county_districts_csv(csv_file)

        # APPLING should come before BIBB
        assert records[0].county_name == "APPLING"

    def test_trailing_comma_in_house_districts(self, tmp_path: Path) -> None:
        """Real data has trailing commas in split rows (e.g., FULTON)."""
        csv_content = textwrap.dedent("""\
            County,Congressional Districts,Senate Districts,House Districts
            FULTON,"5, 6, 7",14,"25, 47, 48,"
            FULTON,"5, 6, 7",14,"57, 58, 59"
        """)
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(csv_content)

        records = parse_county_districts_csv(csv_file)

        house = [r for r in records if r.boundary_type == "state_house"]
        house_ids = {r.district_identifier for r in house}
        assert house_ids == {"025", "047", "048", "057", "058", "059"}

    def test_real_csv_data(self) -> None:
        """Test against the actual data file if present."""
        csv_path = Path("data/counties-by-districts-2023.csv")
        if not csv_path.exists():
            pytest.skip("Data file not available")

        records = parse_county_districts_csv(csv_path)

        # Should have records for all types
        types = {r.boundary_type for r in records}
        assert types == {"congressional", "state_senate", "state_house"}

        # Bibb should have known districts
        bibb_house = {
            r.district_identifier for r in records if r.county_name == "BIBB" and r.boundary_type == "state_house"
        }
        assert bibb_house == {"142", "143", "144", "145", "149"}

        bibb_cong = {
            r.district_identifier for r in records if r.county_name == "BIBB" and r.boundary_type == "congressional"
        }
        assert bibb_cong == {"002", "008"}
