"""Extended tests for precinct metadata service — covering uncovered functions."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.precinct_metadata_service import (
    _extract_precinct_fields,
    get_precinct_metadata_batch,
    get_precinct_metadata_by_boundary,
    upsert_precinct_metadata,
)


class TestExtractPrecinctFields:
    """Tests for _extract_precinct_fields."""

    def test_full_properties(self) -> None:
        props = {
            "DISTRICT": "123",
            "CTYSOSID": "001",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "CONTY": "060",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
            "AREA": "1234567.89",
        }
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["sos_id"] == "001"
        assert result["fips"] == "13121"
        assert result["fips_county"] == "121"
        assert result["county_name"] == "FULTON"
        assert result["county_number"] == "060"
        assert result["precinct_id"] == "SS01"
        assert result["precinct_name"] == "Sandy Springs 01"
        assert result["area"] == Decimal("1234567.89")

    def test_missing_optional_fields(self) -> None:
        props = {"DISTRICT": "123", "FIPS": "13121"}
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["fips"] == "13121"
        assert "sos_id" not in result

    def test_invalid_area_becomes_none(self) -> None:
        props = {"AREA": "not-a-number", "DISTRICT": "123"}
        result = _extract_precinct_fields(props)
        assert "area" not in result  # Invalid decimal excluded

    def test_empty_properties(self) -> None:
        result = _extract_precinct_fields({})
        assert result == {}

    def test_strips_whitespace(self) -> None:
        props = {"DISTRICT": "  123  ", "CTYNAME": "  FULTON  "}
        result = _extract_precinct_fields(props)
        assert result["sos_district_id"] == "123"
        assert result["county_name"] == "FULTON"


class TestUpsertPrecinctMetadata:
    """Tests for upsert_precinct_metadata."""

    @pytest.mark.asyncio
    async def test_creates_new_record(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        props = {
            "DISTRICT": "123",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
        }

        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is not None
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_record(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()
        existing = MagicMock()

        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute.return_value = result

        props = {
            "DISTRICT": "456",
            "FIPS": "13121",
            "FIPS2": "121",
            "CTYNAME": "FULTON",
            "PRECINCT_I": "SS01",
            "PRECINCT_N": "Sandy Springs 01",
        }

        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is existing
        # Verify fields were updated
        assert existing.sos_district_id == "456"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing_required(self) -> None:
        session = AsyncMock()
        boundary_id = uuid.uuid4()

        # Missing required fields
        props = {"DISTRICT": "123"}
        record = await upsert_precinct_metadata(session, boundary_id, props)
        assert record is None


class TestGetPrecinctMetadataBatch:
    """Tests for get_precinct_metadata_batch."""

    @pytest.mark.asyncio
    async def test_returns_records_by_boundary_id(self) -> None:
        session = AsyncMock()
        bid1 = uuid.uuid4()
        bid2 = uuid.uuid4()

        rec1 = MagicMock()
        rec1.boundary_id = bid1
        rec2 = MagicMock()
        rec2.boundary_id = bid2

        result = MagicMock()
        result.scalars.return_value.all.return_value = [rec1, rec2]
        session.execute.return_value = result

        records = await get_precinct_metadata_batch(session, [bid1, bid2])
        assert bid1 in records
        assert bid2 in records

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self) -> None:
        session = AsyncMock()

        records = await get_precinct_metadata_batch(session, [])
        assert records == {}
        session.execute.assert_not_awaited()


class TestGetPrecinctMetadataByBoundary:
    """Tests for get_precinct_metadata_by_boundary."""

    @pytest.mark.asyncio
    async def test_returns_record_when_found(self) -> None:
        session = AsyncMock()
        record = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = record
        session.execute.return_value = result

        found = await get_precinct_metadata_by_boundary(session, uuid.uuid4())
        assert found is record

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_precinct_metadata_by_boundary(session, uuid.uuid4())
        assert found is None
