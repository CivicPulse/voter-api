"""Integration tests for election event JSONL import service.

Tests the import_election_events function using mocked session/DB
following the same pattern as test_candidate_import_service.py.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.schemas.jsonl.election_event import ElectionEventJSONL


def _write_jsonl(tmp_path: Path, records: list[dict], filename: str = "election-events.jsonl") -> Path:
    """Write records as JSONL file."""
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


def _make_election_event_records(count: int = 2) -> list[dict]:
    """Create valid election event records."""
    records = []
    for i in range(count):
        records.append(
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "event_date": f"2026-05-{19 + i:02d}",
                "event_name": f"Test Election Event {i + 1}",
                "event_type": "general_primary",
                "registration_deadline": "2026-04-20",
                "early_voting_start": "2026-04-27",
                "early_voting_end": "2026-05-15",
            }
        )
    return records


class TestReadJsonl:
    """Tests for the shared JSONL reader utility."""

    def test_read_valid_jsonl(self, tmp_path: Path) -> None:
        """Valid JSONL lines parse successfully."""
        from voter_api.services.jsonl_reader import read_jsonl

        records = _make_election_event_records(2)
        path = _write_jsonl(tmp_path, records)
        valid, errors = read_jsonl(path, ElectionEventJSONL)
        assert len(valid) == 2
        assert len(errors) == 0

    def test_read_invalid_jsonl_line_skipped(self, tmp_path: Path) -> None:
        """Invalid JSON lines are captured as errors, not raised."""
        from voter_api.services.jsonl_reader import read_jsonl

        path = tmp_path / "bad.jsonl"
        with path.open("w") as fh:
            fh.write('{"id": "not-a-uuid", "event_date": "bad"}\n')
            fh.write(json.dumps(_make_election_event_records(1)[0], default=str) + "\n")
        valid, errors = read_jsonl(path, ElectionEventJSONL)
        assert len(valid) == 1
        assert len(errors) == 1

    def test_read_empty_file(self, tmp_path: Path) -> None:
        """Empty JSONL file returns empty lists."""
        from voter_api.services.jsonl_reader import read_jsonl

        path = tmp_path / "empty.jsonl"
        path.write_text("")
        valid, errors = read_jsonl(path, ElectionEventJSONL)
        assert len(valid) == 0
        assert len(errors) == 0


class TestImportElectionEvents:
    """Tests for the election event import service."""

    @pytest.mark.asyncio
    async def test_import_election_events_returns_summary(self) -> None:
        """Import returns a summary with inserted/updated counts."""
        from voter_api.services.election_event_import_service import import_election_events

        session = _make_session_mock()
        records = list(_make_election_event_records(2))

        # Mock execute to return rows simulating inserts
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(is_insert=1),
            MagicMock(is_insert=1),
        ]
        session.execute.return_value = mock_result

        result = await import_election_events(session, records)
        assert result["inserted"] >= 0
        assert result["updated"] >= 0
        assert "skipped" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self) -> None:
        """Dry-run mode returns counts without writing to DB."""
        from voter_api.services.election_event_import_service import import_election_events

        session = _make_session_mock()
        # Mock SELECT for existing IDs (empty = all would be inserted)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        records = _make_election_event_records(3)
        result = await import_election_events(session, records, dry_run=True)
        assert result["would_insert"] == 3
        assert result["would_update"] == 0
        # Commit should NOT be called in dry-run
        session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_reimport_returns_updates_not_inserts(self) -> None:
        """Second import of the same records reports updates (0 inserts)."""
        from voter_api.services.election_event_import_service import import_election_events

        session = _make_session_mock()
        records = _make_election_event_records(3)

        # Simulate all rows already existing — UPSERT triggers UPDATE path (xmax != 0)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(is_insert=0),
            MagicMock(is_insert=0),
            MagicMock(is_insert=0),
        ]
        session.execute.return_value = mock_result

        result = await import_election_events(session, records)
        assert result["inserted"] == 0
        assert result["updated"] == 3
        assert result["errors"] == []


class TestImportElections:
    """Tests for the election import service."""

    @pytest.mark.asyncio
    async def test_import_elections_returns_summary(self) -> None:
        """Import returns a summary with inserted/updated counts."""
        from voter_api.services.election_import_service import import_elections

        session = _make_session_mock()
        records = [
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "election_event_id": str(uuid.uuid4()),
                "name": "Governor - Republican Primary",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "election_stage": "election",
                "district": "Governor",
            },
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock(is_insert=1)]
        session.execute.return_value = mock_result

        result = await import_elections(session, records)
        assert result["inserted"] >= 0
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_reimport_returns_updates_not_inserts(self) -> None:
        """Second import of the same records reports updates, not inserts."""
        from voter_api.services.election_import_service import import_elections

        session = _make_session_mock()
        records = [
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "election_event_id": str(uuid.uuid4()),
                "name": "Governor - Republican Primary",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "election_stage": "election",
                "district": "Governor",
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "election_event_id": str(uuid.uuid4()),
                "name": "Lt. Governor - Republican Primary",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "election_stage": "election",
                "district": "Lt. Governor",
            },
        ]

        # Simulate all rows being updates (xmax != 0 -> is_insert = 0)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(is_insert=0),
            MagicMock(is_insert=0),
        ]
        session.execute.return_value = mock_result

        result = await import_elections(session, records)
        assert result["inserted"] == 0
        assert result["updated"] == 2
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self) -> None:
        """Dry-run mode returns counts without writing to DB."""
        from voter_api.services.election_import_service import import_elections

        election_id = uuid.uuid4()
        records = [
            {
                "schema_version": 1,
                "id": str(election_id),
                "election_event_id": str(uuid.uuid4()),
                "name": "Governor - Republican Primary",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "election_stage": "election",
                "district": "Governor",
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "election_event_id": str(uuid.uuid4()),
                "name": "Lt. Governor - Republican Primary",
                "election_date": "2026-05-19",
                "election_type": "general_primary",
                "election_stage": "election",
                "district": "Lt. Governor",
            },
        ]

        session = _make_session_mock()
        # Simulate one existing record (election_id already in DB)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [uuid.UUID(str(election_id))]
        session.execute.return_value = mock_result

        result = await import_elections(session, records, dry_run=True)
        assert result["would_insert"] == 1
        assert result["would_update"] == 1
        session.commit.assert_not_called()


class TestImportCandidacies:
    """Tests for the candidacy import service."""

    @pytest.mark.asyncio
    async def test_import_candidacies_returns_summary(self) -> None:
        """Import returns a summary with inserted/updated counts."""
        from voter_api.services.candidacy_import_service import import_candidacies

        session = _make_session_mock()
        records = [
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "qualified",
                "is_incumbent": False,
            },
        ]

        mock_result = MagicMock()
        mock_result.all.return_value = [MagicMock(is_insert=1)]
        session.execute.return_value = mock_result

        result = await import_candidacies(session, records)
        assert result["inserted"] >= 0
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_reimport_returns_updates_not_inserts(self) -> None:
        """Second import of the same candidacy records reports updates, not inserts."""
        from voter_api.services.candidacy_import_service import import_candidacies

        session = _make_session_mock()
        records = [
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "qualified",
                "is_incumbent": False,
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "qualified",
                "is_incumbent": True,
                "party": "Republican",
            },
        ]

        # All rows are updates on reimport (is_insert = 0)
        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(is_insert=0),
            MagicMock(is_insert=0),
        ]
        session.execute.return_value = mock_result

        result = await import_candidacies(session, records)
        assert result["inserted"] == 0
        assert result["updated"] == 2
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self) -> None:
        """Dry-run mode returns counts without writing to DB."""
        from voter_api.services.candidacy_import_service import import_candidacies

        existing_id = uuid.uuid4()
        records = [
            {
                "schema_version": 1,
                "id": str(existing_id),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "qualified",
                "is_incumbent": False,
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "qualified",
                "is_incumbent": True,
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "candidate_id": str(uuid.uuid4()),
                "election_id": str(uuid.uuid4()),
                "filing_status": "withdrawn",
                "is_incumbent": False,
            },
        ]

        session = _make_session_mock()
        # One record already exists in the DB
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [uuid.UUID(str(existing_id))]
        session.execute.return_value = mock_result

        result = await import_candidacies(session, records, dry_run=True)
        assert result["would_insert"] == 2
        assert result["would_update"] == 1
        session.commit.assert_not_called()


class TestImportCandidateJsonl:
    """Tests for the candidate JSONL person-entity import service."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self) -> None:
        """Dry-run mode returns counts without writing to DB."""
        from voter_api.services.candidate_import_service import import_candidates_jsonl

        existing_id = uuid.uuid4()
        records = [
            {
                "schema_version": 1,
                "id": str(existing_id),
                "full_name": "Jane Smith",
            },
            {
                "schema_version": 1,
                "id": str(uuid.uuid4()),
                "full_name": "John Doe",
            },
        ]

        session = _make_session_mock()
        # One candidate already exists in the DB
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [uuid.UUID(str(existing_id))]
        session.execute.return_value = mock_result

        result = await import_candidates_jsonl(session, records, dry_run=True)
        assert result["would_insert"] == 1
        assert result["would_update"] == 1
        session.commit.assert_not_called()
