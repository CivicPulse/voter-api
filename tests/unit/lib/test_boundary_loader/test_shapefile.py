"""Unit tests for shapefile boundary reader."""

from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import LineString, MultiPolygon, Polygon

from voter_api.lib.boundary_loader.shapefile import (
    MAX_SHAPEFILE_SIZE_BYTES,
    _extract_field,
    _is_remainder_polygon,
    _serialize_value,
    read_shapefile,
)


def _make_gdf(
    geometries: list,
    columns: dict | None = None,
    crs: str = "EPSG:4326",
) -> gpd.GeoDataFrame:
    """Helper to create a GeoDataFrame for testing."""
    data = columns or {}
    return gpd.GeoDataFrame(data, geometry=geometries, crs=crs)


class TestReadShapefile:
    """Tests for read_shapefile function."""

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_valid_single_polygon(self, mock_read: object, tmp_path: Path) -> None:
        """Single Polygon is converted to MultiPolygon."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf([poly], {"NAME": ["District 1"], "GEOID": ["01"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].name == "District 1"
        assert boundaries[0].boundary_identifier == "01"
        assert boundaries[0].geometry.geom_type == "MultiPolygon"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_multipolygon_passthrough(self, mock_read: object, tmp_path: Path) -> None:
        """MultiPolygon geometry passes through unchanged."""
        multi = MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])])
        gdf = _make_gdf([multi], {"NAME": ["Multi"], "GEOID": ["02"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].geometry.geom_type == "MultiPolygon"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_empty_shapefile_raises(self, mock_read: object, tmp_path: Path) -> None:
        """Empty shapefile raises ValueError."""
        gdf = gpd.GeoDataFrame({"geometry": []})
        gdf = gdf.set_geometry("geometry")
        mock_read.return_value = gdf

        shp = tmp_path / "empty.shp"
        shp.write_bytes(b"fake")

        with pytest.raises(ValueError, match="empty"):
            read_shapefile(shp)

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_crs_transformation(self, mock_read: object, tmp_path: Path) -> None:
        """Non-4326 CRS is transformed to EPSG:4326."""
        poly = Polygon([(500000, 4000000), (500100, 4000000), (500100, 4000100), (500000, 4000100)])
        gdf = _make_gdf([poly], {"NAME": ["Projected"], "GEOID": ["01"]}, crs="EPSG:32617")
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        # Verify coordinates are now in lon/lat range
        coords = list(boundaries[0].geometry.geoms[0].exterior.coords)
        for lon, lat in coords:
            assert -180 <= lon <= 180
            assert -90 <= lat <= 90

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_unsupported_geometry_skipped(self, mock_read: object, tmp_path: Path) -> None:
        """Non-polygon geometries are skipped."""
        line = LineString([(0, 0), (1, 1)])
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf([line, poly], {"NAME": ["Line", "Poly"], "GEOID": ["01", "02"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].name == "Poly"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_null_geometry_skipped(self, mock_read: object, tmp_path: Path) -> None:
        """Rows with null geometry are skipped."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        # Create GDF with only valid geometry, then set first to None via pandas
        gdf = _make_gdf([poly, poly], {"NAME": ["Null", "Valid"], "GEOID": ["01", "02"]})
        gdf.loc[0, "geometry"] = None
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].name == "Valid"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_properties_extracted(self, mock_read: object, tmp_path: Path) -> None:
        """Non-geometry columns are extracted into properties."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf(
            [poly],
            {"NAME": ["Test"], "GEOID": ["42"], "POPULATION": [np.int64(1000)]},
        )
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert boundaries[0].properties["POPULATION"] == 1000
        assert isinstance(boundaries[0].properties["POPULATION"], int)

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_name_from_namelsad_column(self, mock_read: object, tmp_path: Path) -> None:
        """Name is extracted from NAMELSAD column when NAME is absent."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf([poly], {"NAMELSAD": ["District 1"], "DISTRICTID": ["D01"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].name == "District 1"
        assert boundaries[0].boundary_identifier == "D01"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_no_identifier_column_skips_row(self, mock_read: object, tmp_path: Path) -> None:
        """Rows with no identifier column are skipped (remainder polygons)."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf([poly], {"NAME": ["Test"], "OTHER_COL": ["value"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 0

    def test_file_size_limit(self, tmp_path: Path) -> None:
        """Oversized file raises ValueError."""
        shp = tmp_path / "big.shp"
        # Create a file that reports as oversized via mock
        shp.write_bytes(b"x")

        with patch.object(Path, "stat") as mock_stat, patch.object(Path, "is_file", return_value=True):
            mock_stat.return_value.st_size = MAX_SHAPEFILE_SIZE_BYTES + 1
            with pytest.raises(ValueError, match="exceeds maximum size"):
                read_shapefile(shp)

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_nan_name_produces_fallback(self, mock_read: object, tmp_path: Path) -> None:
        """NaN NAME column falls back to generic 'Boundary N' name."""
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        gdf = _make_gdf([poly], {"NAME": [float("nan")], "GEOID": ["01"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].name == "Boundary 1"
        assert boundaries[0].boundary_identifier == "01"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_nan_identifier_skipped(self, mock_read: object, tmp_path: Path) -> None:
        """Rows with NaN identifier columns are skipped (remainder polygons)."""
        polys = [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            Polygon([(-86, 30), (-80, 30), (-80, 35), (-86, 35), (-86, 30)]),
        ]
        gdf = _make_gdf(
            polys,
            {"DISTRICT": ["001", np.nan]},
        )
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].boundary_identifier == "001"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_remainder_polygon_with_id_fallback_skipped(self, mock_read: object, tmp_path: Path) -> None:
        """Remainder polygon with NaN DISTRICT but valid ID is skipped.

        Reproduces the bibbsb shapefile bug where a statewide remainder polygon
        (DISTRICT=NaN, ID=6) was imported as a school_board boundary.
        """
        polys = [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            Polygon([(-86, 30), (-80, 30), (-80, 35), (-86, 35), (-86, 30)]),
        ]
        gdf = _make_gdf(
            polys,
            {"DISTRICT": ["001", np.nan], "ID": [1, 6]},
        )
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 1
        assert boundaries[0].boundary_identifier == "001"

    @patch("voter_api.lib.boundary_loader.shapefile.gpd.read_file")
    def test_multiple_boundaries(self, mock_read: object, tmp_path: Path) -> None:
        """Multiple features are parsed correctly."""
        polys = [
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
            Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)]),
        ]
        gdf = _make_gdf(polys, {"NAME": ["D1", "D2"], "GEOID": ["01", "02"]})
        mock_read.return_value = gdf

        shp = tmp_path / "test.shp"
        shp.write_bytes(b"fake")

        boundaries = read_shapefile(shp)
        assert len(boundaries) == 2
        assert boundaries[0].name == "D1"
        assert boundaries[1].name == "D2"


class TestExtractField:
    """Tests for _extract_field helper."""

    def test_finds_first_match(self) -> None:
        """Returns the first matching candidate value."""
        row = {"NAME": "Test", "GEOID": "42"}
        assert _extract_field(row, ["NAME", "GEOID"]) == "Test"

    def test_skips_empty(self) -> None:
        """Skips empty string values."""
        row = {"NAME": "  ", "GEOID": "42"}
        assert _extract_field(row, ["NAME", "GEOID"]) == "42"

    def test_skips_nan_float(self) -> None:
        """Skips float NaN values and returns next valid candidate."""
        row = {"NAME": float("nan"), "GEOID": "42"}
        assert _extract_field(row, ["NAME", "GEOID"]) == "42"

    def test_skips_numpy_nan(self) -> None:
        """Skips numpy NaN values and returns next valid candidate."""
        row = {"NAME": np.float64("nan"), "GEOID": "42"}
        assert _extract_field(row, ["NAME", "GEOID"]) == "42"

    def test_returns_none_when_no_match(self) -> None:
        """Returns None when no candidates match."""
        row = {"OTHER": "val"}
        assert _extract_field(row, ["NAME", "GEOID"]) is None


class TestIsRemainderPolygon:
    """Tests for _is_remainder_polygon helper."""

    def test_nan_district_detected(self) -> None:
        """Row with NaN DISTRICT is detected as remainder."""
        row = {"DISTRICT": float("nan"), "ID": 6}
        columns = ["DISTRICT", "ID", "geometry"]
        assert _is_remainder_polygon(row, columns) is True

    def test_valid_district_not_detected(self) -> None:
        """Row with valid DISTRICT is not a remainder."""
        row = {"DISTRICT": "001", "ID": 1}
        columns = ["DISTRICT", "ID", "geometry"]
        assert _is_remainder_polygon(row, columns) is False

    def test_no_district_column_not_detected(self) -> None:
        """Row without DISTRICT/DISTRICTID columns is not detected."""
        row = {"GEOID": "13001", "ID": 1}
        columns = ["GEOID", "ID", "geometry"]
        assert _is_remainder_polygon(row, columns) is False

    def test_nan_districtid_detected(self) -> None:
        """Row with NaN DISTRICTID is detected as remainder."""
        row = {"DISTRICTID": np.float64("nan"), "ID": 6}
        columns = ["DISTRICTID", "ID", "geometry"]
        assert _is_remainder_polygon(row, columns) is True


class TestSerializeValue:
    """Tests for _serialize_value helper."""

    def test_numpy_integer(self) -> None:
        assert _serialize_value(np.int64(42)) == 42
        assert isinstance(_serialize_value(np.int64(42)), int)

    def test_numpy_float(self) -> None:
        assert _serialize_value(np.float64(3.14)) == 3.14
        assert isinstance(_serialize_value(np.float64(3.14)), float)

    def test_numpy_array(self) -> None:
        result = _serialize_value(np.array([1, 2, 3]))
        assert result == [1, 2, 3]

    def test_regular_value_passthrough(self) -> None:
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(42) == 42

    def test_nan_returns_none(self) -> None:
        assert _serialize_value(float("nan")) is None

    def test_numpy_nan_returns_none(self) -> None:
        assert _serialize_value(np.float64("nan")) is None

    def test_inf_returns_none(self) -> None:
        assert _serialize_value(float("inf")) is None
