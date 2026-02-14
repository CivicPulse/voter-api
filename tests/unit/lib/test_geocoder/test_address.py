"""Unit tests for geocoder address reconstruction, normalization, and parsing."""

from voter_api.lib.geocoder.address import (
    AddressComponents,
    normalize_directional,
    normalize_freeform_address,
    normalize_street_type,
    parse_address_components,
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


class TestNormalizeFreeformAddress:
    """Tests for normalize_freeform_address()."""

    def test_basic_normalization(self) -> None:
        """Basic address gets uppercased and trimmed."""
        result = normalize_freeform_address("100 Peachtree St NW, Atlanta, GA 30303")
        assert result == "100 PEACHTREE ST NW, ATLANTA, GA 30303"

    def test_usps_street_type_abbreviation(self) -> None:
        """Full street types get abbreviated."""
        result = normalize_freeform_address("100 Peachtree Street NW, Atlanta, GA")
        assert "ST" in result
        assert "STREET" not in result

    def test_usps_directional_abbreviation(self) -> None:
        """Full directionals get abbreviated."""
        result = normalize_freeform_address("100 North Main Avenue, Atlanta, GA")
        assert result == "100 N MAIN AVE, ATLANTA, GA"

    def test_collapse_whitespace(self) -> None:
        """Multiple spaces collapsed to single space."""
        result = normalize_freeform_address("100   Peachtree   Street, Atlanta, GA")
        assert "  " not in result

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert normalize_freeform_address("") == ""

    def test_whitespace_only(self) -> None:
        """Whitespace-only returns empty string."""
        assert normalize_freeform_address("   ") == ""

    def test_long_address_500_chars(self) -> None:
        """Addresses up to 500 chars are handled."""
        long_addr = "A" * 500
        result = normalize_freeform_address(long_addr)
        assert len(result) == 500

    def test_already_abbreviated(self) -> None:
        """Already abbreviated address is unchanged after uppercasing."""
        result = normalize_freeform_address("100 PEACHTREE ST NW, ATLANTA, GA 30303")
        assert result == "100 PEACHTREE ST NW, ATLANTA, GA 30303"

    def test_word_boundary_matching(self) -> None:
        """Abbreviations only apply to whole words, not substrings."""
        result = normalize_freeform_address("100 Eastwood Drive, Atlanta, GA")
        # "East" in "Eastwood" should NOT be abbreviated to "E"
        assert "EASTWOOD" in result


class TestAddressComponents:
    """Tests for AddressComponents dataclass."""

    def test_to_dict(self) -> None:
        """to_dict returns keys matching Address model columns."""
        components = AddressComponents(
            street_number="100",
            street_name="PEACHTREE",
            street_type="ST",
            city="ATLANTA",
            state="GA",
            zipcode="30303",
        )
        d = components.to_dict()
        assert d["street_number"] == "100"
        assert d["street_name"] == "PEACHTREE"
        assert d["street_type"] == "ST"
        assert d["city"] == "ATLANTA"
        assert d["state"] == "GA"
        assert d["zipcode"] == "30303"
        assert d["pre_direction"] is None
        assert d["post_direction"] is None
        assert d["apt_unit"] is None

    def test_to_dict_all_none(self) -> None:
        """Default components are all None."""
        components = AddressComponents()
        d = components.to_dict()
        assert all(v is None for v in d.values())


class TestParseAddressComponents:
    """Tests for parse_address_components()."""

    def test_full_georgia_address(self) -> None:
        """Parse a full Georgia address with all components."""
        result = parse_address_components("100 Peachtree St NW, Atlanta, GA 30303")
        assert result.street_number == "100"
        assert result.street_name == "PEACHTREE"
        assert result.street_type == "ST"
        assert result.post_direction == "NW"
        assert result.city == "ATLANTA"
        assert result.state == "GA"
        assert result.zipcode == "30303"

    def test_partial_address_no_zip(self) -> None:
        """Parse address missing ZIP code."""
        result = parse_address_components("100 Main Street, Atlanta, GA")
        assert result.street_number == "100"
        assert result.street_name == "MAIN"
        assert result.street_type == "ST"
        assert result.city == "ATLANTA"
        assert result.state == "GA"
        assert result.zipcode is None

    def test_address_with_unit(self) -> None:
        """Parse address with apartment/unit."""
        result = parse_address_components("456 Peachtree Rd APT 4B, Atlanta, GA 30305")
        assert result.street_number == "456"
        assert result.street_name == "PEACHTREE"
        assert result.street_type == "RD"
        assert result.apt_unit is not None
        assert "4B" in result.apt_unit

    def test_address_with_pre_direction(self) -> None:
        """Parse address with pre-directional."""
        result = parse_address_components("200 N Main St, Atlanta, GA 30303")
        assert result.pre_direction == "N"
        assert result.street_name == "MAIN"

    def test_empty_string(self) -> None:
        """Empty string returns empty components."""
        result = parse_address_components("")
        assert result.street_number is None
        assert result.street_name is None

    def test_zip_plus_4(self) -> None:
        """ZIP+4 format is extracted."""
        result = parse_address_components("100 Main St, Atlanta, GA 30303-1234")
        assert result.zipcode == "30303-1234"

    def test_street_only(self) -> None:
        """Street line only, no city/state."""
        result = parse_address_components("100 Main Street")
        assert result.street_number == "100"
        assert result.street_name == "MAIN"
        assert result.street_type == "ST"
        assert result.city is None
        assert result.state is None

    def test_whitespace_only(self) -> None:
        """Whitespace-only returns empty components."""
        result = parse_address_components("   ")
        assert result.street_number is None
