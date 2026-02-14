"""Unit tests for Georgia coordinate validation and meter-to-degree conversion."""

import pytest

from voter_api.lib.geocoder.point_lookup import (
    GA_MAX_LAT,
    GA_MAX_LNG,
    GA_MIN_LAT,
    GA_MIN_LNG,
    meters_to_degrees,
    validate_georgia_coordinates,
)


class TestValidateGeorgiaCoordinates:
    """Tests for validate_georgia_coordinates()."""

    def test_inside_georgia(self) -> None:
        """Coordinates inside Georgia pass validation."""
        validate_georgia_coordinates(33.749, -84.388)  # Atlanta

    def test_outside_georgia_north(self) -> None:
        """Coordinates north of Georgia raise ValueError."""
        with pytest.raises(ValueError, match="outside the Georgia service area"):
            validate_georgia_coordinates(36.0, -84.0)

    def test_outside_georgia_south(self) -> None:
        """Coordinates south of Georgia raise ValueError."""
        with pytest.raises(ValueError, match="outside the Georgia service area"):
            validate_georgia_coordinates(29.0, -84.0)

    def test_outside_georgia_east(self) -> None:
        """Coordinates east of Georgia raise ValueError."""
        with pytest.raises(ValueError, match="outside the Georgia service area"):
            validate_georgia_coordinates(33.0, -79.0)

    def test_outside_georgia_west(self) -> None:
        """Coordinates west of Georgia raise ValueError."""
        with pytest.raises(ValueError, match="outside the Georgia service area"):
            validate_georgia_coordinates(33.0, -87.0)

    def test_boundary_edge_min_lat(self) -> None:
        """Southern boundary edge passes."""
        validate_georgia_coordinates(GA_MIN_LAT, -83.0)

    def test_boundary_edge_max_lat(self) -> None:
        """Northern boundary edge passes."""
        validate_georgia_coordinates(GA_MAX_LAT, -83.0)

    def test_boundary_edge_min_lng(self) -> None:
        """Western boundary edge passes."""
        validate_georgia_coordinates(33.0, GA_MIN_LNG)

    def test_boundary_edge_max_lng(self) -> None:
        """Eastern boundary edge passes."""
        validate_georgia_coordinates(33.0, GA_MAX_LNG)

    def test_new_york_coordinates(self) -> None:
        """New York coordinates are outside Georgia."""
        with pytest.raises(ValueError):
            validate_georgia_coordinates(40.7128, -74.0060)


class TestMetersToDegrees:
    """Tests for meters_to_degrees()."""

    def test_zero_meters(self) -> None:
        """Zero meters returns 0.0."""
        assert meters_to_degrees(0, 33.0) == 0.0

    def test_100_meters_at_georgia_latitude(self) -> None:
        """100m at 33°N returns a reasonable degree value."""
        result = meters_to_degrees(100, 33.0)
        # At 33°N, 100m ≈ 0.001 degrees latitude
        assert 0.0008 < result < 0.0015

    def test_larger_at_higher_latitude(self) -> None:
        """Degree conversion is larger at higher latitudes (for longitude)."""
        result_30 = meters_to_degrees(100, 30.0)
        result_35 = meters_to_degrees(100, 35.0)
        # At higher latitude, longitude degrees are smaller, so more degrees needed
        assert result_35 > result_30

    def test_negative_meters_returns_zero(self) -> None:
        """Negative meters returns 0.0."""
        assert meters_to_degrees(-10, 33.0) == 0.0

    def test_small_distance(self) -> None:
        """1 meter returns a small positive value."""
        result = meters_to_degrees(1, 33.0)
        assert result > 0
        assert result < 0.001
