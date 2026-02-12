"""Tests for county metadata service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.county_metadata_service import (
    get_county_metadata_by_geoid,
    import_county_metadata,
)


def _mock_session(*, existing: object | None = None) -> AsyncMock:
    """Create a mock async session.

    Args:
        existing: If provided, scalar_one_or_none returns this value
            (simulates an existing record). Otherwise returns None.
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    session.execute.return_value = mock_result
    return session


def _sample_record(**overrides: object) -> dict:
    """Build a sample county metadata dict with sensible defaults."""
    base = {
        "geoid": "13121",
        "fips_state": "13",
        "fips_county": "121",
        "name": "Fulton",
        "name_lsad": "Fulton County",
        "gnis_code": "01694833",
        "geoid_fq": "0500000US13121",
        "lsad_code": "06",
        "class_fp": "H1",
        "mtfcc": "G4020",
        "csa_code": "122",
        "cbsa_code": "12060",
        "metdiv_code": "12054",
        "functional_status": "A",
        "land_area_m2": 1364558845,
        "water_area_m2": 20564942,
        "internal_point_lat": "+33.7900338",
        "internal_point_lon": "-084.4681816",
    }
    base.update(overrides)
    return base


class TestImportCountyMetadata:
    """Tests for import_county_metadata."""

    @pytest.mark.asyncio
    async def test_inserts_new_record(self) -> None:
        """New records are added to the session."""
        session = _mock_session(existing=None)

        count = await import_county_metadata(session, [_sample_record()])

        assert count == 1
        session.add.assert_called_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_updates_existing_record(self) -> None:
        """Existing records are updated in place."""
        existing = MagicMock()
        existing.geoid = "13121"
        session = _mock_session(existing=existing)

        count = await import_county_metadata(session, [_sample_record(name="Fulton Updated")])

        assert count == 1
        assert existing.name == "Fulton Updated"
        session.add.assert_not_called()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_record_without_geoid(self) -> None:
        """Records missing geoid are skipped."""
        session = _mock_session(existing=None)

        count = await import_county_metadata(session, [{"name": "No GEOID"}])

        assert count == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_records(self) -> None:
        """Multiple records are processed."""
        session = _mock_session(existing=None)

        records = [
            _sample_record(geoid="13121"),
            _sample_record(geoid="13067", name="Bibb", fips_county="067"),
        ]
        count = await import_county_metadata(session, records)

        assert count == 2
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """Empty input returns zero."""
        session = _mock_session()

        count = await import_county_metadata(session, [])

        assert count == 0
        session.commit.assert_awaited_once()


class TestGetCountyMetadataByGeoid:
    """Tests for get_county_metadata_by_geoid."""

    @pytest.mark.asyncio
    async def test_returns_record_when_found(self) -> None:
        """Returns the record when GEOID exists."""
        mock_record = MagicMock()
        mock_record.geoid = "13121"
        session = _mock_session(existing=mock_record)

        result = await get_county_metadata_by_geoid(session, "13121")

        assert result is mock_record

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        """Returns None when GEOID does not exist."""
        session = _mock_session(existing=None)

        result = await get_county_metadata_by_geoid(session, "99999")

        assert result is None
