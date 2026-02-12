"""Tests for county metadata Pydantic schemas."""

from unittest.mock import MagicMock

from voter_api.schemas.county_metadata import CountyMetadataResponse


class TestCountyMetadataResponse:
    """Tests for CountyMetadataResponse schema."""

    def test_validates_from_dict(self) -> None:
        """Schema validates from a plain dict."""
        data = {
            "geoid": "13121",
            "fips_state": "13",
            "fips_county": "121",
            "name": "Fulton",
            "name_lsad": "Fulton County",
            "land_area_m2": 1364558845,
            "water_area_m2": 20564942,
        }
        response = CountyMetadataResponse(**data)
        assert response.geoid == "13121"
        assert response.name == "Fulton"

    def test_from_attributes_with_orm_object(self) -> None:
        """Schema validates from an ORM-like object using from_attributes."""
        obj = MagicMock()
        obj.geoid = "13121"
        obj.fips_state = "13"
        obj.fips_county = "121"
        obj.gnis_code = "01694833"
        obj.geoid_fq = "0500000US13121"
        obj.name = "Fulton"
        obj.name_lsad = "Fulton County"
        obj.lsad_code = "06"
        obj.class_fp = "H1"
        obj.mtfcc = "G4020"
        obj.csa_code = "122"
        obj.cbsa_code = "12060"
        obj.metdiv_code = "12054"
        obj.functional_status = "A"
        obj.land_area_m2 = 1364558845
        obj.water_area_m2 = 20564942
        obj.internal_point_lat = "+33.7900338"
        obj.internal_point_lon = "-084.4681816"

        response = CountyMetadataResponse.model_validate(obj)
        assert response.geoid == "13121"
        assert response.fips_state == "13"
        assert response.name_lsad == "Fulton County"

    def test_computed_land_area_km2(self) -> None:
        """land_area_km2 computed field converts m2 to km2."""
        response = CountyMetadataResponse(
            geoid="13121",
            fips_state="13",
            fips_county="121",
            name="Fulton",
            name_lsad="Fulton County",
            land_area_m2=1364558845,
        )
        assert response.land_area_km2 == 1364.56

    def test_computed_water_area_km2(self) -> None:
        """water_area_km2 computed field converts m2 to km2."""
        response = CountyMetadataResponse(
            geoid="13121",
            fips_state="13",
            fips_county="121",
            name="Fulton",
            name_lsad="Fulton County",
            water_area_m2=20564942,
        )
        assert response.water_area_km2 == 20.56

    def test_computed_fields_none_when_area_missing(self) -> None:
        """Computed km2 fields return None when m2 values are not set."""
        response = CountyMetadataResponse(
            geoid="13121",
            fips_state="13",
            fips_county="121",
            name="Fulton",
            name_lsad="Fulton County",
        )
        assert response.land_area_km2 is None
        assert response.water_area_km2 is None

    def test_nullable_fields_default_to_none(self) -> None:
        """Optional fields default to None."""
        response = CountyMetadataResponse(
            geoid="13121",
            fips_state="13",
            fips_county="121",
            name="Fulton",
            name_lsad="Fulton County",
        )
        assert response.gnis_code is None
        assert response.csa_code is None
        assert response.cbsa_code is None
        assert response.metdiv_code is None

    def test_serialization_includes_computed_fields(self) -> None:
        """model_dump includes computed fields."""
        response = CountyMetadataResponse(
            geoid="13121",
            fips_state="13",
            fips_county="121",
            name="Fulton",
            name_lsad="Fulton County",
            land_area_m2=1000000,
            water_area_m2=500000,
        )
        data = response.model_dump()
        assert "land_area_km2" in data
        assert "water_area_km2" in data
        assert data["land_area_km2"] == 1.0
        assert data["water_area_km2"] == 0.5
