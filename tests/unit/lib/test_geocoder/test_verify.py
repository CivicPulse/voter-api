"""Unit tests for address verification — validate_address_components()."""

from voter_api.lib.geocoder.address import AddressComponents
from voter_api.lib.geocoder.verify import validate_address_components


class TestValidateAddressComponents:
    """Tests for validate_address_components()."""

    def test_well_formed_address(self) -> None:
        """Well-formed address reports all required components present."""
        components = AddressComponents(
            street_number="100",
            street_name="PEACHTREE",
            street_type="ST",
            post_direction="NW",
            city="ATLANTA",
            state="GA",
            zipcode="30303",
        )
        result = validate_address_components(components)
        assert result.is_well_formed is True
        assert len(result.missing_components) == 0
        assert len(result.malformed_components) == 0
        assert "street_number" in result.present_components
        assert "street_name" in result.present_components
        assert "city" in result.present_components
        assert "state" in result.present_components
        assert "zip" in result.present_components

    def test_partial_address_missing_components(self) -> None:
        """Partial address reports missing components."""
        components = AddressComponents(
            street_number="100",
            street_name="PEACHTREE",
        )
        result = validate_address_components(components)
        assert result.is_well_formed is False
        assert "city" in result.missing_components
        assert "state" in result.missing_components
        assert "zip" in result.missing_components

    def test_malformed_zip_detected(self) -> None:
        """Malformed ZIP code is reported."""
        components = AddressComponents(
            street_number="100",
            street_name="MAIN",
            city="ATLANTA",
            state="GA",
            zipcode="ABCDE",
        )
        result = validate_address_components(components)
        assert result.is_well_formed is False
        assert len(result.malformed_components) == 1
        assert result.malformed_components[0].component == "zip"

    def test_valid_zip_plus_4(self) -> None:
        """ZIP+4 format is accepted."""
        components = AddressComponents(
            street_number="100",
            street_name="MAIN",
            city="ATLANTA",
            state="GA",
            zipcode="30303-1234",
        )
        result = validate_address_components(components)
        assert result.is_well_formed is True
        assert len(result.malformed_components) == 0

    def test_empty_components(self) -> None:
        """All-empty components reports all required as missing."""
        components = AddressComponents()
        result = validate_address_components(components)
        assert result.is_well_formed is False
        assert len(result.missing_components) == 5

    def test_optional_components_detected(self) -> None:
        """Optional components (street_type, direction, unit) are detected when present."""
        components = AddressComponents(
            street_number="100",
            pre_direction="N",
            street_name="MAIN",
            street_type="ST",
            post_direction="NW",
            apt_unit="APT 4B",
            city="ATLANTA",
            state="GA",
            zipcode="30303",
        )
        result = validate_address_components(components)
        assert "street_type" in result.present_components
        assert "pre_direction" in result.present_components
        assert "post_direction" in result.present_components
        assert "unit" in result.present_components
