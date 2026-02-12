"""Tests for the exporter public API."""

import json
from pathlib import Path

import pytest

from voter_api.lib.exporter import (
    SUPPORTED_FORMATS,
    ExportResult,
    export_voters,
)


class TestExporterPublicAPI:
    """Tests for the exporter __init__ module."""

    def test_supported_formats(self) -> None:
        assert "csv" in SUPPORTED_FORMATS
        assert "json" in SUPPORTED_FORMATS
        assert "geojson" in SUPPORTED_FORMATS

    def test_export_csv(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        records = [{"voter_registration_number": "12345", "county": "FULTON"}]
        result = export_voters(records, "csv", output)
        assert isinstance(result, ExportResult)
        assert result.record_count == 1
        assert result.file_size_bytes > 0
        assert output.exists()

    def test_export_json(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        records = [{"voter_registration_number": "12345"}]
        result = export_voters(records, "json", output)
        assert result.record_count == 1
        data = json.loads(output.read_text())
        assert len(data) == 1

    def test_export_geojson(self, tmp_path: Path) -> None:
        output = tmp_path / "test.geojson"
        records = [{"voter_registration_number": "12345", "latitude": 33.7, "longitude": -84.3}]
        result = export_voters(records, "geojson", output)
        assert result.record_count == 1
        data = json.loads(output.read_text())
        assert data["type"] == "FeatureCollection"

    def test_unsupported_format_raises(self, tmp_path: Path) -> None:
        output = tmp_path / "test.xml"
        with pytest.raises(ValueError, match="Unsupported format"):
            export_voters([], "xml", output)

    def test_export_csv_with_custom_columns(self, tmp_path: Path) -> None:
        output = tmp_path / "test.csv"
        records = [{"a": 1, "b": 2, "c": 3}]
        result = export_voters(records, "csv", output, columns=["a", "b"])
        assert result.record_count == 1

    def test_export_result_has_output_path(self, tmp_path: Path) -> None:
        output = tmp_path / "test.json"
        result = export_voters([], "json", output)
        assert result.output_path == output
