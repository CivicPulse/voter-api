"""Unit tests for Census Bureau geocoder provider."""

from voter_api.lib.geocoder.census import CensusGeocoder


class TestCensusResponseParsing:
    """Tests for Census API response parsing."""

    def setup_method(self) -> None:
        self.geocoder = CensusGeocoder()

    def test_successful_match(self) -> None:
        """Successful address match returns GeocodingResult."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 N MAIN ST, ATLANTA, GA, 30301",
                        "coordinates": {"x": -84.3880, "y": 33.7490},
                        "tigerLine": {"tigerLineId": "12345"},
                    }
                ]
            }
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.latitude == 33.7490
        assert result.longitude == -84.3880
        assert result.confidence_score == 1.0
        assert result.matched_address == "123 N MAIN ST, ATLANTA, GA, 30301"

    def test_no_matches(self) -> None:
        """No matches returns None."""
        data = {"result": {"addressMatches": []}}
        assert self.geocoder._parse_response(data) is None

    def test_missing_coordinates(self) -> None:
        """Missing coordinates returns None."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST",
                        "coordinates": {},
                    }
                ]
            }
        }
        assert self.geocoder._parse_response(data) is None

    def test_malformed_response(self) -> None:
        """Malformed response returns None."""
        assert self.geocoder._parse_response({}) is None
        assert self.geocoder._parse_response({"result": {}}) is None

    def test_no_tigerline_lower_confidence(self) -> None:
        """Result without tigerLine gets lower confidence."""
        data = {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "123 MAIN ST",
                        "coordinates": {"x": -84.0, "y": 33.0},
                    }
                ]
            }
        }
        result = self.geocoder._parse_response(data)
        assert result is not None
        assert result.confidence_score == 0.8


class TestGetGeocoder:
    """Tests for geocoder provider registry."""

    def test_get_census(self) -> None:
        """Census geocoder is available by name."""
        from voter_api.lib.geocoder import get_geocoder

        geocoder = get_geocoder("census")
        assert geocoder.provider_name == "census"

    def test_unknown_provider(self) -> None:
        """Unknown provider raises ValueError."""
        import pytest

        from voter_api.lib.geocoder import get_geocoder

        with pytest.raises(ValueError, match="Unknown geocoder provider"):
            get_geocoder("nonexistent")
