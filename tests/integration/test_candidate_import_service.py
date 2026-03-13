"""Integration tests for candidate import service.

Tests the process_candidate_import function using mocked session/DB
following the same pattern as test_voter_history_import.py.
"""

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.models.import_job import ImportJob
from voter_api.services.candidate_import_service import (
    process_candidate_import,
)


def _make_import_job(**overrides: object) -> MagicMock:
    """Build a mock ImportJob for testing."""
    defaults = {
        "id": uuid.uuid4(),
        "file_name": "candidates.jsonl",
        "file_type": "candidate_import",
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


def _write_jsonl(tmp_path: Path, records: list[dict], filename: str = "candidates.jsonl") -> Path:
    """Write candidate records as JSONL file."""
    f = tmp_path / filename
    with f.open("w") as fh:
        for record in records:
            fh.write(json.dumps(record, default=str) + "\n")
    return f


def _make_session_mock() -> AsyncMock:
    """Create a session mock."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_candidate_records(count: int = 2) -> list[dict]:
    """Create a list of valid candidate records."""
    records = []
    for i in range(count):
        records.append(
            {
                "election_name": f"US Senate District {i + 1}",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "candidate_name": f"Test Candidate {i + 1}",
                "party": "Republican",
                "filing_status": "qualified",
                "is_incumbent": False,
                "contest_name": f"US Senate District {i + 1}",
                "qualified_date": "2026-03-01",
                "occupation": "Attorney",
                "email": f"candidate{i + 1}@test.com",
                "county": "FULTON",
                "municipality": None,
            }
        )
    return records


class TestProcessCandidateImport:
    """Tests for the candidate import service function."""

    async def test_successful_import(self, tmp_path: Path) -> None:
        """Successful import updates job with correct counts."""
        records = _make_candidate_records(2)
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(2, 0),
            ) as mock_upsert,
        ):
            result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.status == "completed"
        assert result.total_records == 2
        assert result.records_succeeded == 2
        assert result.records_failed == 0
        assert result.records_inserted == 2
        assert result.records_updated == 0
        mock_upsert.assert_awaited_once()

    async def test_invalid_records_counted_as_failed(self, tmp_path: Path) -> None:
        """Records with parse errors are counted as failed."""
        records = [
            {
                "election_name": "US Senate",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "candidate_name": "Valid Candidate",
                "party": "Republican",
                "filing_status": "qualified",
                "is_incumbent": False,
            },
            {
                # Missing required fields
                "election_name": "",
                "election_date": "2026-05-19",
                "candidate_name": "",
            },
        ]
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
        ):
            result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.status == "completed"
        assert result.total_records == 2
        # The second record has parse errors (_parse_error set by validator)
        assert result.records_failed >= 1

    async def test_election_auto_creation(self, tmp_path: Path) -> None:
        """Election is resolved for each batch of records."""
        records = _make_candidate_records(1)
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        election_id = uuid.uuid4()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=election_id,
            ) as mock_resolve,
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
        ):
            await process_candidate_import(session, job, jsonl_file, batch_size=10)

        # _resolve_election called once per record
        assert mock_resolve.await_count == 1

    async def test_upsert_updates_on_reimport(self, tmp_path: Path) -> None:
        """Re-import of same candidates results in updates, not inserts."""
        records = _make_candidate_records(2)
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(0, 2),  # 0 inserts, 2 updates
            ),
        ):
            result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.records_inserted == 0
        assert result.records_updated == 2
        assert result.records_succeeded == 2

    async def test_exception_marks_job_failed(self, tmp_path: Path) -> None:
        """Exception during processing marks job as failed."""
        records = _make_candidate_records(1)
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB error"),
            ),
            pytest.raises(RuntimeError, match="DB error"),
        ):
            await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert job.status == "failed"

    async def test_website_links_processed(self, tmp_path: Path) -> None:
        """Website links trigger candidate link creation."""
        records = [
            {
                "election_name": "US Senate",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "candidate_name": "Test Candidate",
                "party": "Republican",
                "filing_status": "qualified",
                "is_incumbent": False,
                "website": "https://example.com",
                "county": "FULTON",
            },
        ]
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()
        candidate_id = uuid.uuid4()

        # Mock the candidate lookup for link creation
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = candidate_id
        session.execute.return_value = mock_result

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_links",
                new_callable=AsyncMock,
            ) as mock_links,
        ):
            result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.status == "completed"
        mock_links.assert_awaited_once()
        link_args = mock_links.call_args[0]
        assert link_args[1][0]["link_type"] == "website"
        assert link_args[1][0]["url"] == "https://example.com"

    async def test_job_lifecycle_pending_to_running_to_completed(self, tmp_path: Path) -> None:
        """Job transitions from pending -> running -> completed."""
        records = _make_candidate_records(1)
        jsonl_file = _write_jsonl(tmp_path, records)
        session = _make_session_mock()

        job = _make_import_job()

        # Use a proxy class instead of patching type(mock).status with a property,
        # which would mutate the MagicMock class and leak into later tests.
        _original_setattr = object.__setattr__

        class StatusCapturingJob:
            """Proxy that captures status transitions while delegating everything else."""

            def __init__(self, delegate: MagicMock) -> None:
                _original_setattr(self, "_delegate", delegate)
                _original_setattr(self, "statuses", [])

            def __getattr__(self, name: str):  # noqa: ANN001
                return getattr(self._delegate, name)

            def __setattr__(self, name: str, value: object) -> None:
                if name == "status":
                    self.statuses.append(value)
                    setattr(self._delegate, name, value)
                else:
                    setattr(self._delegate, name, value)

        proxy_job = StatusCapturingJob(job)

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(1, 0),
            ),
        ):
            await process_candidate_import(session, proxy_job, jsonl_file, batch_size=10)

        assert proxy_job.statuses == ["running", "completed"]

    async def test_empty_file(self, tmp_path: Path) -> None:
        """Empty JSONL file completes with zero records."""
        jsonl_file = _write_jsonl(tmp_path, [])
        job = _make_import_job()
        session = _make_session_mock()

        result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.status == "completed"
        assert result.total_records == 0
        assert result.records_succeeded == 0
        assert result.records_failed == 0

    async def test_large_batch_processing(self, tmp_path: Path) -> None:
        """Large file is processed in multiple batches."""
        records = _make_candidate_records(25)
        jsonl_file = _write_jsonl(tmp_path, records)
        job = _make_import_job()
        session = _make_session_mock()

        with (
            patch(
                "voter_api.services.candidate_import_service._resolve_election",
                new_callable=AsyncMock,
                return_value=uuid.uuid4(),
            ),
            patch(
                "voter_api.services.candidate_import_service._upsert_candidate_batch",
                new_callable=AsyncMock,
                return_value=(10, 0),
            ) as mock_upsert,
        ):
            result = await process_candidate_import(session, job, jsonl_file, batch_size=10)

        assert result.total_records == 25
        # 25 records / 10 per batch = 3 upsert calls
        assert mock_upsert.await_count == 3
