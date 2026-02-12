"""Tests for the JSON export writer."""

import json
from pathlib import Path
from uuid import UUID

from voter_api.lib.exporter.json_writer import write_json


class TestJSONWriter:
    """Tests for write_json."""

    def test_writes_array_of_records(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        records = [
            {"voter_registration_number": "12345", "county": "FULTON"},
            {"voter_registration_number": "67890", "county": "DEKALB"},
        ]
        count = write_json(output, records)
        assert count == 2

        data = json.loads(output.read_text())
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["county"] == "FULTON"

    def test_empty_records(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        count = write_json(output, [])
        assert count == 0

        data = json.loads(output.read_text())
        assert data == []

    def test_handles_uuid(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        records = [{"id": test_uuid, "name": "test"}]
        count = write_json(output, records)
        assert count == 1

        data = json.loads(output.read_text())
        assert data[0]["id"] == str(test_uuid)

    def test_handles_none_values(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        records = [{"name": "test", "value": None}]
        write_json(output, records)

        data = json.loads(output.read_text())
        assert data[0]["value"] is None

    def test_valid_json_structure(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        records = [{"a": 1}, {"b": 2}, {"c": 3}]
        write_json(output, records)

        # Should be valid JSON
        content = output.read_text()
        data = json.loads(content)
        assert len(data) == 3
