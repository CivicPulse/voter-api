"""Tests for the export service module."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.export_service import (
    _build_export_query,
    _voter_to_dict,
    create_export_job,
    get_export_job,
    list_export_jobs,
    process_export,
)


def _mock_export_job(**overrides: object) -> MagicMock:
    """Create a mock ExportJob."""
    job = MagicMock()
    job.id = uuid.uuid4()
    job.output_format = "csv"
    job.filters = {}
    job.status = "pending"
    job.record_count = None
    job.file_path = None
    job.file_size_bytes = None
    job.triggered_by = None
    job.requested_at = datetime(2024, 1, 1, tzinfo=UTC)
    job.completed_at = None
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


def _mock_voter(**overrides: object) -> MagicMock:
    """Create a mock Voter for export."""
    voter = MagicMock()
    voter.voter_registration_number = "12345678"
    voter.county = "FULTON"
    voter.status = "ACTIVE"
    voter.last_name = "SMITH"
    voter.first_name = "JOHN"
    voter.middle_name = "A"
    voter.residence_street_number = "123"
    voter.residence_street_name = "MAIN"
    voter.residence_street_type = "ST"
    voter.residence_city = "ATLANTA"
    voter.residence_zipcode = "30301"
    voter.congressional_district = "05"
    voter.state_senate_district = "34"
    voter.state_house_district = "55"
    voter.county_precinct = "SS01"
    voter.geocoded_locations = []
    for key, value in overrides.items():
        setattr(voter, key, value)
    return voter


class TestCreateExportJob:
    """Tests for create_export_job."""

    @pytest.mark.asyncio
    async def test_creates_job(self) -> None:
        session = AsyncMock()

        await create_export_job(
            session,
            output_format="csv",
            filters={"county": "FULTON"},
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert added.output_format == "csv"
        assert added.filters == {"county": "FULTON"}

    @pytest.mark.asyncio
    async def test_creates_job_with_triggered_by(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await create_export_job(
            session,
            output_format="json",
            filters={},
            triggered_by=user_id,
        )

        added = session.add.call_args[0][0]
        assert added.triggered_by == user_id


class TestVoterToDict:
    """Tests for _voter_to_dict."""

    def test_basic_fields(self) -> None:
        voter = _mock_voter()
        result = _voter_to_dict(voter)
        assert result["voter_registration_number"] == "12345678"
        assert result["county"] == "FULTON"
        assert result["last_name"] == "SMITH"
        assert result["first_name"] == "JOHN"

    def test_without_geocoded_location(self) -> None:
        voter = _mock_voter()
        result = _voter_to_dict(voter)
        assert "latitude" not in result
        assert "longitude" not in result

    def test_with_primary_geocoded_location(self) -> None:
        loc = MagicMock()
        loc.is_primary = True
        loc.latitude = 33.749
        loc.longitude = -84.388
        voter = _mock_voter(geocoded_locations=[loc])
        result = _voter_to_dict(voter)
        assert result["latitude"] == 33.749
        assert result["longitude"] == -84.388

    def test_with_non_primary_location_excluded(self) -> None:
        loc = MagicMock()
        loc.is_primary = False
        voter = _mock_voter(geocoded_locations=[loc])
        result = _voter_to_dict(voter)
        assert "latitude" not in result

    def test_with_none_geocoded_locations(self) -> None:
        voter = _mock_voter(geocoded_locations=None)
        result = _voter_to_dict(voter)
        assert "latitude" not in result


class TestBuildExportQuery:
    """Tests for _build_export_query."""

    def test_no_filters(self) -> None:
        query = _build_export_query({})
        assert query is not None

    def test_county_filter(self) -> None:
        query = _build_export_query({"county": "FULTON"})
        assert query is not None

    def test_status_filter(self) -> None:
        query = _build_export_query({"status": "ACTIVE"})
        assert query is not None

    def test_name_filters(self) -> None:
        query = _build_export_query({"first_name": "JOHN", "last_name": "SMITH"})
        assert query is not None

    def test_geographic_filters(self) -> None:
        query = _build_export_query(
            {
                "residence_city": "ATLANTA",
                "residence_zipcode": "30301",
            }
        )
        assert query is not None

    def test_district_filters(self) -> None:
        query = _build_export_query(
            {
                "congressional_district": "05",
                "state_senate_district": "34",
                "state_house_district": "55",
                "county_precinct": "SS01",
            }
        )
        assert query is not None

    def test_present_in_latest_import_filter(self) -> None:
        query = _build_export_query({"present_in_latest_import": True})
        assert query is not None

    def test_present_in_latest_import_none_ignored(self) -> None:
        query = _build_export_query({"present_in_latest_import": None})
        assert query is not None

    def test_analysis_run_id_filter(self) -> None:
        run_id = str(uuid.uuid4())
        query = _build_export_query({"analysis_run_id": run_id})
        assert query is not None

    def test_match_status_filter(self) -> None:
        query = _build_export_query({"match_status": "mismatch"})
        assert query is not None

    def test_combined_analysis_filters(self) -> None:
        run_id = str(uuid.uuid4())
        query = _build_export_query(
            {
                "analysis_run_id": run_id,
                "match_status": "match",
            }
        )
        assert query is not None


class TestProcessExport:
    """Tests for process_export."""

    @pytest.mark.asyncio
    async def test_successful_export(self, tmp_path: Path) -> None:
        session = AsyncMock()
        job = _mock_export_job(output_format="csv")

        mock_result = MagicMock()
        mock_result.record_count = 5
        mock_result.file_size_bytes = 1024
        mock_result.output_path = tmp_path / "export.csv"

        with (
            patch(
                "voter_api.services.export_service._fetch_export_records",
                return_value=[{"name": "test"}],
            ),
            patch(
                "voter_api.services.export_service.export_voters",
                return_value=mock_result,
            ),
        ):
            await process_export(session, job, tmp_path)

        assert job.status == "completed"
        assert job.record_count == 5

    @pytest.mark.asyncio
    async def test_export_failure_sets_failed_status(self, tmp_path: Path) -> None:
        session = AsyncMock()
        job = _mock_export_job()

        with (
            patch(
                "voter_api.services.export_service._fetch_export_records",
                side_effect=RuntimeError("DB error"),
            ),
            pytest.raises(RuntimeError),
        ):
            await process_export(session, job, tmp_path)

        assert job.status == "failed"

    @pytest.mark.asyncio
    async def test_export_formats(self, tmp_path: Path) -> None:
        for fmt in ("csv", "json", "geojson"):
            session = AsyncMock()
            job = _mock_export_job(output_format=fmt)

            mock_result = MagicMock()
            mock_result.record_count = 1
            mock_result.file_size_bytes = 100
            mock_result.output_path = tmp_path / f"export.{fmt}"

            with (
                patch(
                    "voter_api.services.export_service._fetch_export_records",
                    return_value=[],
                ),
                patch(
                    "voter_api.services.export_service.export_voters",
                    return_value=mock_result,
                ),
            ):
                await process_export(session, job, tmp_path)

            assert job.status == "completed"


class TestGetExportJob:
    """Tests for get_export_job."""

    @pytest.mark.asyncio
    async def test_returns_job_when_found(self) -> None:
        job = _mock_export_job()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = job
        session.execute.return_value = result

        found = await get_export_job(session, job.id)
        assert found is job

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_export_job(session, uuid.uuid4())
        assert found is None


class TestListExportJobs:
    """Tests for list_export_jobs."""

    @pytest.mark.asyncio
    async def test_returns_jobs_and_count(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()] * 3
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_export_jobs(session)
        assert total == 3
        assert len(jobs) == 3

    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()]
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_export_jobs(session, status_filter="completed")
        assert total == 1
