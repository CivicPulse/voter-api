"""Integration tests for voter history import service.

Covers:
- T017: Import service — parsing, upsert, re-import, duplicates, errors
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.models.import_job import ImportJob
from voter_api.services.voter_history_service import (
    process_voter_history_import,
)


def _make_import_job(**overrides: object) -> MagicMock:
    """Build a mock ImportJob for testing."""
    defaults = {
        "id": uuid.uuid4(),
        "file_name": "voter_history.csv",
        "file_type": "voter_history",
        "status": "pending",
        "total_records": None,
        "records_succeeded": None,
        "records_failed": None,
        "records_inserted": None,
        "records_updated": None,
        "records_soft_deleted": None,
        "records_skipped": None,
        "records_unmatched": None,
        "error_log": None,
        "last_processed_offset": None,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    job = MagicMock(spec=ImportJob)
    for k, v in defaults.items():
        setattr(job, k, v)
    return job


def _write_csv(tmp_path: Path, rows: list[str]) -> Path:
    """Write a voter history CSV file with standard headers."""
    header = (
        "County Name,Voter Registration Number,Election Date,"
        "Election Type,Party,Ballot Style,Absentee,Provisional,Supplemental"
    )
    f = tmp_path / "voter_history.csv"
    f.write_text(header + "\n" + "\n".join(rows) + "\n")
    return f


def _make_session_mock() -> AsyncMock:
    """Create a session mock that handles execute() for synchronous_commit."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def _mock_vh_optimizations():
    """Mock all DB optimization functions so they don't hit a real database."""
    with (
        patch(
            "voter_api.services.voter_history_service._drop_vh_indexes",
            new_callable=AsyncMock,
        ),
        patch(
            "voter_api.services.voter_history_service._rebuild_vh_indexes",
            new_callable=AsyncMock,
        ),
        patch(
            "voter_api.services.voter_history_service._disable_vh_autovacuum",
            new_callable=AsyncMock,
        ),
        patch(
            "voter_api.services.voter_history_service._enable_vh_autovacuum_and_vacuum",
            new_callable=AsyncMock,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# T017: Import service tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_mock_vh_optimizations")
class TestProcessVoterHistoryImport:
    """Tests for the voter history import service function."""

    @pytest.mark.asyncio
    async def test_successful_import(self, tmp_path: Path) -> None:
        """Successful import updates job with correct counts."""
        rows = [
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N",
            "FULTON,12345679,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N",
        ]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.status == "completed"
        assert result.total_records == 2
        assert result.records_succeeded == 2
        assert result.records_failed == 0
        assert result.records_skipped == 0
        mock_upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_corrupt_records_counted_as_failed(self, tmp_path: Path) -> None:
        """Records with parse errors are counted as failed."""
        rows = [
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N",
            "FULTON,12345679,BAD-DATE,GENERAL ELECTION,NP,STD,N,N,N",
        ]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.status == "completed"
        assert result.total_records == 2
        assert result.records_succeeded == 1
        assert result.records_failed == 1
        assert result.error_log is not None
        assert len(result.error_log) == 1

    @pytest.mark.asyncio
    async def test_duplicate_records_skipped(self, tmp_path: Path) -> None:
        """Duplicate records within same file are skipped."""
        rows = [
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N",
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,Y,N,N",
        ]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.records_succeeded == 1
        assert result.records_skipped == 1

    @pytest.mark.asyncio
    async def test_unmatched_voters_always_zero(self, tmp_path: Path) -> None:
        """Unmatched voter count is always 0 (counting removed for performance)."""
        rows = ["FULTON,99999999,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.records_unmatched == 0

    @pytest.mark.asyncio
    async def test_replace_previous_import_called(self, tmp_path: Path) -> None:
        """Re-import replacement is invoked after successful processing."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ) as mock_replace,
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10)

        mock_replace.assert_awaited_once_with(session, job)

    @pytest.mark.asyncio
    async def test_large_batch_processing(self, tmp_path: Path) -> None:
        """Large file is processed in multiple batches."""
        rows = [f"FULTON,{10000 + i},11/05/2024,GENERAL ELECTION,NP,STD,N,N,N" for i in range(25)]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.total_records == 25
        assert result.records_succeeded == 25
        # 25 records / 10 per batch = 3 upsert calls
        assert mock_upsert.await_count == 3

    @pytest.mark.asyncio
    async def test_exception_marks_job_failed(self, tmp_path: Path) -> None:
        """Exception during processing marks job as failed."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB error"),
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert job.status == "failed"

    @pytest.mark.asyncio
    async def test_missing_required_fields_produce_errors(self, tmp_path: Path) -> None:
        """Rows with missing required fields are counted as failed."""
        rows = [
            ",12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N",  # no county
            "FULTON,,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N",  # no reg number
        ]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.records_failed == 2
        assert result.records_succeeded == 0


class TestOptimizationLifecycle:
    """Tests for DB optimization lifecycle during voter history import."""

    @pytest.mark.asyncio
    async def test_optimizations_applied_by_default(self, tmp_path: Path) -> None:
        """Default call applies DB optimizations (drop indexes, disable autovacuum)."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._drop_vh_indexes",
                new_callable=AsyncMock,
            ) as mock_drop,
            patch(
                "voter_api.services.voter_history_service._rebuild_vh_indexes",
                new_callable=AsyncMock,
            ) as mock_rebuild,
            patch(
                "voter_api.services.voter_history_service._disable_vh_autovacuum",
                new_callable=AsyncMock,
            ) as mock_disable_av,
            patch(
                "voter_api.services.voter_history_service._enable_vh_autovacuum_and_vacuum",
                new_callable=AsyncMock,
            ) as mock_enable_av,
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10)

        mock_drop.assert_awaited_once()
        mock_rebuild.assert_awaited_once()
        mock_disable_av.assert_awaited_once()
        mock_enable_av.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skip_optimizations(self, tmp_path: Path) -> None:
        """skip_optimizations=True skips DB optimizations."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.voter_history_service._drop_vh_indexes",
                new_callable=AsyncMock,
            ) as mock_drop,
            patch(
                "voter_api.services.voter_history_service._rebuild_vh_indexes",
                new_callable=AsyncMock,
            ) as mock_rebuild,
            patch(
                "voter_api.services.voter_history_service._disable_vh_autovacuum",
                new_callable=AsyncMock,
            ) as mock_disable_av,
            patch(
                "voter_api.services.voter_history_service._enable_vh_autovacuum_and_vacuum",
                new_callable=AsyncMock,
            ) as mock_enable_av,
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10, skip_optimizations=True)

        mock_drop.assert_not_awaited()
        mock_rebuild.assert_not_awaited()
        mock_disable_av.assert_not_awaited()
        mock_enable_av.assert_not_awaited()
