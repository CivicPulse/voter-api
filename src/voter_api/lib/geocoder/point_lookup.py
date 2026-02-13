"""Georgia bounding box validation and meter-to-degree conversion for point lookup."""

import math

# Georgia approximate bounding box (WGS84) with small buffer for GPS inaccuracy
GA_MIN_LAT = 30.355
GA_MAX_LAT = 35.001
GA_MIN_LNG = -85.606
GA_MAX_LNG = -80.840


def validate_georgia_coordinates(lat: float, lng: float) -> None:
    """Validate that coordinates fall within the Georgia service area.

    Args:
        lat: WGS84 latitude.
        lng: WGS84 longitude.

    Raises:
        ValueError: If coordinates are outside Georgia's bounding box.
    """
    if not (GA_MIN_LAT <= lat <= GA_MAX_LAT and GA_MIN_LNG <= lng <= GA_MAX_LNG):
        msg = "Coordinates are outside the Georgia service area."
        raise ValueError(msg)


def meters_to_degrees(meters: float, latitude: float) -> float:
    """Convert meters to approximate degrees at a given latitude.

    Uses a latitude-dependent approximation. At Georgia's latitude (30-35°N),
    the error is <3%. For GPS accuracy radii (<1km), this translates to <30m.

    Args:
        meters: Distance in meters.
        latitude: WGS84 latitude for longitude scaling.

    Returns:
        Conservative radius in degrees (max of lat/lng conversions).
    """
    if meters <= 0:
        return 0.0

    lat_deg = meters / 111_320
    lng_deg = meters / (111_320 * math.cos(math.radians(latitude)))
    return max(lat_deg, lng_deg)
