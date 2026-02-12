"""Unit tests for importer validator module."""

from voter_api.lib.importer.validator import is_geocodable, validate_batch, validate_record


class TestValidateRecord:
    """Tests for single record validation."""

    def test_valid_record(self) -> None:
        """Valid record passes validation."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            "first_name": "JOHN",
        }
        is_valid, errors = validate_record(record)
        assert is_valid
        assert errors == []

    def test_missing_required_field(self) -> None:
        """Missing required field fails validation."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            # first_name missing
        }
        is_valid, errors = validate_record(record)
        assert not is_valid
        assert any("first_name" in e for e in errors)

    def test_empty_required_field(self) -> None:
        """Empty string for required field fails validation."""
        record = {
            "county": "",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            "first_name": "JOHN",
        }
        is_valid, errors = validate_record(record)
        assert not is_valid

    def test_valid_birth_year(self) -> None:
        """Valid birth year passes."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            "first_name": "JOHN",
            "birth_year": "1990",
        }
        is_valid, errors = validate_record(record)
        assert is_valid

    def test_invalid_birth_year(self) -> None:
        """Birth year outside range fails."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            "first_name": "JOHN",
            "birth_year": "1800",
        }
        is_valid, errors = validate_record(record)
        assert not is_valid
        assert any("birth_year" in e for e in errors)

    def test_non_numeric_birth_year(self) -> None:
        """Non-numeric birth year fails with format error."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "ACTIVE",
            "last_name": "SMITH",
            "first_name": "JOHN",
            "birth_year": "abc",
        }
        is_valid, errors = validate_record(record)
        assert not is_valid
        assert any("format" in e for e in errors)

    def test_non_standard_status_still_valid(self) -> None:
        """Non-standard status logs warning but doesn't fail validation."""
        record = {
            "county": "Fulton",
            "voter_registration_number": "12345",
            "status": "CUSTOM_STATUS",
            "last_name": "SMITH",
            "first_name": "JOHN",
        }
        is_valid, errors = validate_record(record)
        assert is_valid
        assert errors == []


class TestIsGeocodable:
    """Tests for geocodability check."""

    def test_geocodable_with_street_and_city(self) -> None:
        """Record with street name and city is geocodable."""
        record = {
            "residence_street_name": "MAIN",
            "residence_city": "ATLANTA",
        }
        assert is_geocodable(record)

    def test_not_geocodable_without_street(self) -> None:
        """Record without street name is not geocodable."""
        record = {
            "residence_city": "ATLANTA",
        }
        assert not is_geocodable(record)


class TestValidateBatch:
    """Tests for batch validation."""

    def test_batch_separates_valid_and_invalid(self) -> None:
        """Batch validation separates valid from invalid."""
        records = [
            {
                "county": "Fulton",
                "voter_registration_number": "1",
                "status": "ACTIVE",
                "last_name": "A",
                "first_name": "B",
            },
            {
                "county": "",
                "voter_registration_number": "2",
                "status": "ACTIVE",
                "last_name": "C",
                "first_name": "D",
            },
        ]
        valid, failed = validate_batch(records)
        assert len(valid) == 1
        assert len(failed) == 1
