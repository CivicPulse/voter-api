"""Tests for the CSV export writer."""

import csv
from pathlib import Path

from voter_api.lib.exporter.csv_writer import DEFAULT_COLUMNS, write_csv


class TestCSVWriter:
    """Tests for write_csv."""

    def test_writes_header_and_records(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        records = [
            {"voter_registration_number": "12345", "county": "FULTON", "status": "ACTIVE"},
            {"voter_registration_number": "67890", "county": "DEKALB", "status": "INACTIVE"},
        ]
        count = write_csv(output, records)
        assert count == 2
        assert output.exists()

        with output.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["voter_registration_number"] == "12345"
        assert rows[1]["county"] == "DEKALB"

    def test_uses_default_columns(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        records = [{"voter_registration_number": "12345", "county": "FULTON"}]
        write_csv(output, records)

        with output.open() as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == DEFAULT_COLUMNS

    def test_custom_columns(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        columns = ["voter_registration_number", "county"]
        records = [{"voter_registration_number": "12345", "county": "FULTON", "status": "ACTIVE"}]
        write_csv(output, records, columns=columns)

        with output.open() as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == columns

    def test_empty_records(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        count = write_csv(output, [])
        assert count == 0
        assert output.exists()

        with output.open() as f:
            reader = csv.reader(f)
            header = next(reader)
            rows = list(reader)
        assert header == DEFAULT_COLUMNS
        assert len(rows) == 0

    def test_handles_special_characters(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        records = [{"voter_registration_number": '12345,"quoted"', "county": "O'BRIEN"}]
        count = write_csv(output, records)
        assert count == 1

        with output.open() as f:
            reader = csv.DictReader(f)
            row = next(reader)
        assert row["voter_registration_number"] == '12345,"quoted"'
        assert row["county"] == "O'BRIEN"
