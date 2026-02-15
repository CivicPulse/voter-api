"""Unit tests for the officials library base module."""

from datetime import date

import pytest

from voter_api.lib.officials.base import BaseOfficialsProvider, OfficialRecord, OfficialsProviderError


class TestOfficialRecord:
    """Tests for OfficialRecord dataclass."""

    def test_minimal_record(self) -> None:
        """Record with only required fields."""
        rec = OfficialRecord(
            source_name="test_source",
            source_record_id="rec-001",
            boundary_type="congressional",
            district_identifier="5",
            full_name="Nikema Williams",
        )
        assert rec.source_name == "test_source"
        assert rec.full_name == "Nikema Williams"
        assert rec.party is None
        assert rec.raw_data == {}

    def test_record_is_frozen(self) -> None:
        """Mutating a frozen OfficialRecord raises AttributeError."""
        rec = OfficialRecord(
            source_name="test",
            source_record_id="001",
            boundary_type="congressional",
            district_identifier="5",
            full_name="Nikema Williams",
        )
        with pytest.raises(AttributeError):
            rec.full_name = "Changed Name"

    def test_full_record(self) -> None:
        """Record with all fields populated."""
        rec = OfficialRecord(
            source_name="open_states",
            source_record_id="ocd-person/abc-123",
            boundary_type="state_senate",
            district_identifier="39",
            full_name="Sally Harrell",
            first_name="Sally",
            last_name="Harrell",
            party="Democratic",
            title="State Senator",
            photo_url="https://example.com/photo.jpg",
            term_start_date=date(2023, 1, 9),
            term_end_date=date(2025, 1, 13),
            website="https://example.com",
            email="senator@example.com",
            phone="404-555-0100",
            office_address="18 Capitol Square, Atlanta, GA",
            raw_data={"id": "ocd-person/abc-123", "name": "Sally Harrell"},
        )
        assert rec.party == "Democratic"
        assert rec.term_start_date == date(2023, 1, 9)
        assert rec.raw_data["id"] == "ocd-person/abc-123"


class TestOfficialsProviderError:
    """Tests for OfficialsProviderError."""

    def test_error_message(self) -> None:
        """Error formats provider name and message."""
        err = OfficialsProviderError("open_states", "rate limited", status_code=429)
        assert "open_states" in str(err)
        assert "rate limited" in str(err)
        assert err.status_code == 429
        assert err.provider_name == "open_states"

    def test_error_no_status_code(self) -> None:
        """Error without status code."""
        err = OfficialsProviderError("congress_gov", "connection timeout")
        assert err.status_code is None


class TestBaseOfficialsProvider:
    """Tests for BaseOfficialsProvider ABC."""

    def test_cannot_instantiate(self) -> None:
        """Cannot instantiate abstract class."""
        with pytest.raises(TypeError):
            BaseOfficialsProvider()

    def test_concrete_subclass(self) -> None:
        """Concrete subclass can be instantiated."""

        class MockProvider(BaseOfficialsProvider):
            @property
            def provider_name(self) -> str:
                return "mock"

            async def fetch_by_district(self, boundary_type: str, district_identifier: str) -> list[OfficialRecord]:
                return []

        provider = MockProvider()
        assert provider.provider_name == "mock"

    @pytest.mark.asyncio
    async def test_fetch_by_point_not_implemented(self) -> None:
        """Default fetch_by_point raises NotImplementedError."""

        class MockProvider(BaseOfficialsProvider):
            @property
            def provider_name(self) -> str:
                return "mock"

            async def fetch_by_district(self, boundary_type: str, district_identifier: str) -> list[OfficialRecord]:
                return []

        provider = MockProvider()
        with pytest.raises(NotImplementedError, match="mock does not support geo-lookup"):
            await provider.fetch_by_point(33.749, -84.388)
