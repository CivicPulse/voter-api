"""Unit tests for boundary file manifest and zip extraction."""

import zipfile
from pathlib import Path

import pytest

from voter_api.lib.boundary_loader.manifest import (
    BOUNDARY_MANIFEST,
    BoundaryFileEntry,
    find_shp_in_zip,
    get_manifest,
    resolve_zip_path,
)
from voter_api.models.boundary import BOUNDARY_TYPES


class TestBoundaryManifest:
    """Tests for the BOUNDARY_MANIFEST data."""

    def test_all_entries_have_valid_boundary_types(self) -> None:
        """Every manifest entry has a boundary_type in BOUNDARY_TYPES."""
        for entry in BOUNDARY_MANIFEST:
            assert entry.boundary_type in BOUNDARY_TYPES, (
                f"{entry.zip_filename} has invalid boundary_type: {entry.boundary_type}"
            )

    def test_filenames_are_unique(self) -> None:
        """All zip filenames in the manifest are unique."""
        filenames = [e.zip_filename for e in BOUNDARY_MANIFEST]
        assert len(filenames) == len(set(filenames))

    def test_manifest_has_expected_count(self) -> None:
        """Manifest contains all 8 expected entries."""
        assert len(BOUNDARY_MANIFEST) == 8

    def test_county_entries_have_county_set(self) -> None:
        """Entries with source='county' have a county name."""
        for entry in BOUNDARY_MANIFEST:
            if entry.source == "county":
                assert entry.county is not None, f"{entry.zip_filename} is county-source but has no county"

    def test_state_fips_only_on_county_type(self) -> None:
        """Only the county boundary type has state_fips set."""
        for entry in BOUNDARY_MANIFEST:
            if entry.state_fips:
                assert entry.boundary_type == "county"


class TestGetManifest:
    """Tests for get_manifest function."""

    def test_returns_copy(self) -> None:
        """get_manifest returns a copy, not the original list."""
        manifest = get_manifest()
        assert manifest == BOUNDARY_MANIFEST
        assert manifest is not BOUNDARY_MANIFEST

    def test_mutation_does_not_affect_original(self) -> None:
        """Mutating the returned list does not change BOUNDARY_MANIFEST."""
        manifest = get_manifest()
        original_len = len(BOUNDARY_MANIFEST)
        manifest.pop()
        assert len(BOUNDARY_MANIFEST) == original_len


class TestResolveZipPath:
    """Tests for resolve_zip_path function."""

    def test_resolves_path(self, tmp_path: Path) -> None:
        """Resolves a zip path from data dir and entry."""
        entry = BoundaryFileEntry(zip_filename="test.zip", boundary_type="congressional", source="state")
        result = resolve_zip_path(tmp_path, entry)
        assert result == tmp_path / "test.zip"


class TestFindShpInZip:
    """Tests for find_shp_in_zip function."""

    def test_finds_shp_in_flat_zip(self, tmp_path: Path) -> None:
        """Finds .shp file in a flat zip archive."""
        zip_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("boundary.shp", b"fake shapefile data")
            zf.writestr("boundary.dbf", b"fake dbf data")
            zf.writestr("boundary.shx", b"fake shx data")

        result = find_shp_in_zip(zip_path, extract_dir)
        assert result.suffix == ".shp"
        assert result.exists()

    def test_finds_shp_in_nested_zip(self, tmp_path: Path) -> None:
        """Finds .shp file nested in subdirectory within zip."""
        zip_path = tmp_path / "test.zip"
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("subdir/boundary.shp", b"fake shapefile data")
            zf.writestr("subdir/boundary.dbf", b"fake dbf data")

        result = find_shp_in_zip(zip_path, extract_dir)
        assert result.suffix == ".shp"
        assert result.exists()

    def test_empty_zip_raises(self, tmp_path: Path) -> None:
        """Raises ValueError when zip contains no .shp file."""
        zip_path = tmp_path / "empty.zip"
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no shapefile here")

        with pytest.raises(ValueError, match="No .shp file found"):
            find_shp_in_zip(zip_path, extract_dir)

    def test_invalid_zip_raises(self, tmp_path: Path) -> None:
        """Raises BadZipFile for invalid zip archives."""
        zip_path = tmp_path / "bad.zip"
        zip_path.write_bytes(b"not a zip file")
        extract_dir = tmp_path / "extract"
        extract_dir.mkdir()

        with pytest.raises(zipfile.BadZipFile):
            find_shp_in_zip(zip_path, extract_dir)
