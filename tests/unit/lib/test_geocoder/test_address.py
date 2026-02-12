"""Unit tests for geocoder address reconstruction and normalization."""

from voter_api.lib.geocoder.address import (
    normalize_directional,
    normalize_street_type,
    reconstruct_address,
)


class TestNormalizeDirectional:
    """Tests for directional normalization."""

    def test_full_word(self) -> None:
        """Full directional word is abbreviated."""
        assert normalize_directional("NORTH") == "N"
        assert normalize_directional("SOUTHWEST") == "SW"

    def test_already_abbreviated(self) -> None:
        """Already abbreviated directional is returned as-is."""
        assert normalize_directional("N") == "N"
        assert normalize_directional("SE") == "SE"

    def test_case_insensitive(self) -> None:
        """Normalization is case-insensitive."""
        assert normalize_directional("north") == "N"
        assert normalize_directional("South") == "S"


class TestNormalizeStreetType:
    """Tests for street type normalization."""

    def test_full_word(self) -> None:
        """Full street type is abbreviated."""
        assert normalize_street_type("STREET") == "ST"
        assert normalize_street_type("AVENUE") == "AVE"
        assert normalize_street_type("BOULEVARD") == "BLVD"

    def test_already_abbreviated(self) -> None:
        """Already abbreviated type is returned as-is."""
        assert normalize_street_type("ST") == "ST"
        assert normalize_street_type("AVE") == "AVE"


class TestReconstructAddress:
    """Tests for full address reconstruction."""

    def test_full_address(self) -> None:
        """Full address with all components."""
        result = reconstruct_address(
            street_number="123",
            pre_direction="NORTH",
            street_name="MAIN",
            street_type="STREET",
            city="ATLANTA",
            zipcode="30301",
        )
        assert result == "123 N MAIN ST, ATLANTA, GA 30301"

    def test_minimal_address(self) -> None:
        """Address with only street name and city."""
        result = reconstruct_address(
            street_name="MAIN",
            city="ATLANTA",
        )
        assert result == "MAIN, ATLANTA, GA"

    def test_empty_street_name(self) -> None:
        """Empty street name returns empty string."""
        assert reconstruct_address(street_name=None) == ""
        assert reconstruct_address(street_name="") == ""

    def test_with_apartment(self) -> None:
        """Address with apartment/unit number."""
        result = reconstruct_address(
            street_number="456",
            street_name="PEACHTREE",
            street_type="ROAD",
            apt_unit="4B",
            city="ATLANTA",
            zipcode="30305",
        )
        assert result == "456 PEACHTREE RD APT 4B, ATLANTA, GA 30305"

    def test_apt_with_prefix(self) -> None:
        """Apartment already has prefix — no double prefixing."""
        result = reconstruct_address(
            street_number="789",
            street_name="OAK",
            street_type="DRIVE",
            apt_unit="STE 100",
            city="SAVANNAH",
        )
        assert result == "789 OAK DR STE 100, SAVANNAH, GA"

    def test_post_direction(self) -> None:
        """Address with post-direction."""
        result = reconstruct_address(
            street_number="100",
            street_name="PEACHTREE",
            street_type="STREET",
            post_direction="NORTHWEST",
            city="ATLANTA",
        )
        assert result == "100 PEACHTREE ST NW, ATLANTA, GA"

    def test_leading_zeros_stripped(self) -> None:
        """Leading zeros in street number are stripped."""
        result = reconstruct_address(
            street_number="0042",
            street_name="ELM",
            street_type="LANE",
            city="MACON",
        )
        assert result == "42 ELM LN, MACON, GA"

    def test_missing_components_no_extra_spaces(self) -> None:
        """Missing components don't produce extra spaces."""
        result = reconstruct_address(
            street_number="10",
            pre_direction=None,
            street_name="BROAD",
            street_type=None,
            post_direction="",
            city="COLUMBUS",
        )
        assert result == "10 BROAD, COLUMBUS, GA"
        assert "  " not in result

    def test_empty_component_strings(self) -> None:
        """Empty strings are treated as missing."""
        result = reconstruct_address(
            street_number="",
            pre_direction="",
            street_name="WALNUT",
            street_type="",
            apt_unit="",
            city="AUGUSTA",
            zipcode="",
        )
        assert result == "WALNUT, AUGUSTA, GA"
