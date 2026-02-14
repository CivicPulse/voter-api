"""Tests for the import service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.import_service import (
    create_import_job,
    get_import_diff,
    get_import_job,
    list_import_jobs,
)


def _mock_import_job(**overrides: object) -> MagicMock:
    """Create a mock ImportJob."""
    job = MagicMock()
    job.id = uuid.uuid4()
    job.file_name = "voters.csv"
    job.file_type = "voter_csv"
    job.status = "pending"
    job.total_records = None
    job.records_succeeded = None
    job.records_failed = None
    job.records_inserted = None
    job.records_updated = None
    job.records_soft_deleted = None
    job.error_log = None
    job.last_processed_offset = None
    job.triggered_by = None
    job.started_at = None
    job.completed_at = None
    job.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(job, key, value)
    return job


class TestCreateImportJob:
    """Tests for create_import_job."""

    @pytest.mark.asyncio
    async def test_creates_job(self) -> None:
        session = AsyncMock()

        await create_import_job(
            session,
            file_name="voters.csv",
            file_type="voter_csv",
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert added.file_name == "voters.csv"
        assert added.file_type == "voter_csv"
        assert added.status == "pending"

    @pytest.mark.asyncio
    async def test_creates_job_with_triggered_by(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await create_import_job(
            session,
            file_name="boundaries.geojson",
            file_type="geojson",
            triggered_by=user_id,
        )

        added = session.add.call_args[0][0]
        assert added.triggered_by == user_id

    @pytest.mark.asyncio
    async def test_default_file_type_is_voter_csv(self) -> None:
        session = AsyncMock()

        await create_import_job(session, file_name="data.csv")

        added = session.add.call_args[0][0]
        assert added.file_type == "voter_csv"


class TestGetImportJob:
    """Tests for get_import_job."""

    @pytest.mark.asyncio
    async def test_returns_job_when_found(self) -> None:
        job = _mock_import_job()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = job
        session.execute.return_value = result

        found = await get_import_job(session, job.id)
        assert found is job

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_import_job(session, uuid.uuid4())
        assert found is None


class TestListImportJobs:
    """Tests for list_import_jobs."""

    @pytest.mark.asyncio
    async def test_returns_jobs_and_count(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 5
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()] * 5
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_import_jobs(session)
        assert total == 5
        assert len(jobs) == 5

    @pytest.mark.asyncio
    async def test_filter_by_file_type(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()] * 2
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_import_jobs(session, file_type="voter_csv")
        assert total == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()]
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_import_jobs(session, status="completed")
        assert total == 1

    @pytest.mark.asyncio
    async def test_combined_filters(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_import_jobs(session, file_type="shapefile", status="failed")
        assert total == 0
        assert jobs == []

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        jobs, total = await list_import_jobs(session, page=3, page_size=10)
        assert total == 50


class TestGetImportDiff:
    """Tests for get_import_diff."""

    @pytest.mark.asyncio
    async def test_returns_none_when_job_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        diff = await get_import_diff(session, uuid.uuid4())
        assert diff is None

    @pytest.mark.asyncio
    async def test_returns_diff_for_existing_job(self) -> None:
        job = _mock_import_job()
        session = AsyncMock()

        # Mock responses: get_import_job, added, removed, updated
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = job

        added_result = MagicMock()
        added_result.scalars.return_value.all.return_value = ["REG001", "REG002"]

        removed_result = MagicMock()
        removed_result.scalars.return_value.all.return_value = ["REG003"]

        updated_result = MagicMock()
        updated_result.scalars.return_value.all.return_value = ["REG004"]

        session.execute.side_effect = [job_result, added_result, removed_result, updated_result]

        diff = await get_import_diff(session, job.id)
        assert diff is not None
        assert diff.job_id == job.id
        assert diff.added == ["REG001", "REG002"]
        assert diff.removed == ["REG003"]
        assert diff.updated == ["REG004"]
