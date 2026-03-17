"""Unit tests for CapabilitiesResponse schema."""

from voter_api.schemas.election import CapabilitiesResponse


class TestCapabilitiesResponse:
    """Tests for the CapabilitiesResponse Pydantic model."""

    def test_supported_filters_shape(self):
        """supported_filters contains expected filter names."""
        resp = CapabilitiesResponse(
            supported_filters=["q", "race_category", "county", "district", "election_date"],
            endpoints={"filter_options": True},
        )
        assert resp.supported_filters == ["q", "race_category", "county", "district", "election_date"]

    def test_endpoints_shape(self):
        """endpoints dict contains filter_options flag."""
        resp = CapabilitiesResponse(
            supported_filters=["q"],
            endpoints={"filter_options": True},
        )
        assert resp.endpoints == {"filter_options": True}

    def test_serialization(self):
        """Model serializes to dict with correct keys."""
        resp = CapabilitiesResponse(
            supported_filters=["q", "race_category", "county", "district", "election_date"],
            endpoints={"filter_options": True},
        )
        data = resp.model_dump()
        assert set(data.keys()) == {"supported_filters", "endpoints"}
        assert isinstance(data["supported_filters"], list)
        assert isinstance(data["endpoints"], dict)
