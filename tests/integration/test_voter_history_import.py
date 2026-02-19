"""Integration tests for voter history import service.

Covers:
- T017: Import service — parsing, upsert, re-import, unmatched, duplicates, errors
- T031: Election auto-creation during import
"""

import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.models.import_job import ImportJob
from voter_api.services.voter_history_service import process_voter_history_import


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


# ---------------------------------------------------------------------------
# T017: Import service tests
# ---------------------------------------------------------------------------


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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
            ),
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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
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
    async def test_unmatched_voters_counted(self, tmp_path: Path) -> None:
        """Unmatched voter registration numbers are tracked."""
        rows = ["FULTON,99999999,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=1,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.records_unmatched == 1

    @pytest.mark.asyncio
    async def test_replace_previous_import_called(self, tmp_path: Path) -> None:
        """Re-import replacement is invoked after successful processing."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ) as mock_upsert,
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
            ),
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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB error"),
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
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
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            result = await process_voter_history_import(session, job, csv_file, batch_size=10)

        assert result.records_failed == 2
        assert result.records_succeeded == 0


# ---------------------------------------------------------------------------
# T031: Election auto-creation
# ---------------------------------------------------------------------------


class TestElectionAutoCreation:
    """Tests for election auto-creation during import."""

    @pytest.mark.asyncio
    async def test_auto_create_called(self, tmp_path: Path) -> None:
        """Auto-create elections is invoked during import."""
        rows = ["FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N"]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=1,
            ) as mock_create,
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10)

        mock_create.assert_awaited_once()
        # First arg is session, second is the valid records list
        records = mock_create.call_args[0][1]
        assert len(records) == 1
        assert records[0]["election_date"] == date(2024, 11, 5)

    @pytest.mark.asyncio
    async def test_multiple_election_types_in_batch(self, tmp_path: Path) -> None:
        """Batch with multiple election types triggers auto-creation for each."""
        rows = [
            "FULTON,12345678,11/05/2024,GENERAL ELECTION,NP,STD,N,N,N",
            "FULTON,12345678,05/21/2024,GENERAL PRIMARY,DEM,STD,N,N,N",
        ]
        csv_file = _write_csv(tmp_path, rows)
        job = _make_import_job()
        session = AsyncMock()

        with (
            patch(
                "voter_api.services.voter_history_service._upsert_voter_history_batch",
                new_callable=AsyncMock,
            ),
            patch(
                "voter_api.services.voter_history_service._auto_create_elections",
                new_callable=AsyncMock,
                return_value=2,
            ) as mock_create,
            patch(
                "voter_api.services.voter_history_service._count_unmatched_voters",
                new_callable=AsyncMock,
                return_value=0,
            ),
            patch(
                "voter_api.services.voter_history_service._replace_previous_import",
                new_callable=AsyncMock,
            ),
        ):
            await process_voter_history_import(session, job, csv_file, batch_size=10)

        mock_create.assert_awaited_once()
        records = mock_create.call_args[0][1]
        assert len(records) == 2
