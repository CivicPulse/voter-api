"""Tests for the county-district service module."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.county_district_service import import_county_districts


class TestImportCountyDistricts:
    """Tests for import_county_districts."""

    @pytest.mark.asyncio
    async def test_inserts_new_records(self) -> None:
        session = AsyncMock()

        mock_record = MagicMock()
        mock_record.county_name = "FULTON"
        mock_record.boundary_type = "congressional"
        mock_record.district_identifier = "05"

        # No existing record
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        with patch(
            "voter_api.services.county_district_service.parse_county_districts_csv",
            return_value=[mock_record],
        ):
            count = await import_county_districts(session, Path("test.csv"))

        assert count == 1
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_existing_records(self) -> None:
        session = AsyncMock()

        mock_record = MagicMock()
        mock_record.county_name = "FULTON"
        mock_record.boundary_type = "congressional"
        mock_record.district_identifier = "05"

        # Existing record found
        existing = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        session.execute.return_value = result

        with patch(
            "voter_api.services.county_district_service.parse_county_districts_csv",
            return_value=[mock_record],
        ):
            count = await import_county_districts(session, Path("test.csv"))

        assert count == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_file(self) -> None:
        session = AsyncMock()

        with patch(
            "voter_api.services.county_district_service.parse_county_districts_csv",
            return_value=[],
        ):
            count = await import_county_districts(session, Path("empty.csv"))

        assert count == 0

    @pytest.mark.asyncio
    async def test_mixed_new_and_existing(self) -> None:
        session = AsyncMock()

        rec1 = MagicMock()
        rec1.county_name = "FULTON"
        rec1.boundary_type = "congressional"
        rec1.district_identifier = "05"

        rec2 = MagicMock()
        rec2.county_name = "DEKALB"
        rec2.boundary_type = "congressional"
        rec2.district_identifier = "04"

        # First record exists, second doesn't
        existing = MagicMock()
        result_existing = MagicMock()
        result_existing.scalar_one_or_none.return_value = existing
        result_new = MagicMock()
        result_new.scalar_one_or_none.return_value = None
        session.execute.side_effect = [result_existing, result_new]

        with patch(
            "voter_api.services.county_district_service.parse_county_districts_csv",
            return_value=[rec1, rec2],
        ):
            count = await import_county_districts(session, Path("test.csv"))

        assert count == 1
