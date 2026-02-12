"""Tests for voter schemas."""

from voter_api.schemas.voter import AddressResponse


class TestAddressResponse:
    """Tests for AddressResponse computed_field."""

    def test_full_address_basic(self) -> None:
        addr = AddressResponse(
            street_number="123",
            street_name="MAIN",
            street_type="ST",
            city="ATLANTA",
            zipcode="30303",
        )
        assert addr.full_address == "123 MAIN ST, ATLANTA, 30303"

    def test_full_address_with_apt(self) -> None:
        addr = AddressResponse(
            street_number="456",
            street_name="OAK",
            street_type="AVE",
            apt_unit_number="2B",
            city="DECATUR",
            zipcode="30030",
        )
        assert "APT 2B" in addr.full_address
        assert addr.full_address == "456 OAK AVE APT 2B, DECATUR, 30030"

    def test_full_address_with_directions(self) -> None:
        addr = AddressResponse(
            street_number="789",
            pre_direction="NW",
            street_name="PEACHTREE",
            street_type="RD",
            post_direction="NE",
            city="ATLANTA",
        )
        assert addr.full_address == "789 NW PEACHTREE RD NE, ATLANTA"

    def test_full_address_empty(self) -> None:
        addr = AddressResponse()
        assert addr.full_address == ""

    def test_full_address_no_city_zip(self) -> None:
        addr = AddressResponse(street_number="100", street_name="ELM")
        assert addr.full_address == "100 ELM"
