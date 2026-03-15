"""Unit tests for election_import_service._prepare_record.

Tests the placeholder UUID handling to ensure that the well-known
00000000-0000-0000-0000-000000000000 placeholder is treated as None
and not converted to a uuid.UUID FK reference.
"""

import uuid

import pytest

from voter_api.services.election_import_service import _prepare_record

PLACEHOLDER_UUID = "00000000-0000-0000-0000-000000000000"
REAL_UUID = "12345678-1234-5678-1234-567812345678"


class TestPrepareRecordElectionEventId:
    """Tests for election_event_id handling in _prepare_record."""

    def test_placeholder_uuid_produces_none(self) -> None:
        """Placeholder election_event_id should be excluded (treated as None).

        The converter writes 00000000-0000-0000-0000-000000000000 as a
        placeholder when no election_event can be resolved at conversion
        time. The import service must not forward this as a real FK value.
        """
        record = {
            "id": REAL_UUID,
            "name": "Test Election",
            "election_date": "2026-03-10",
            "election_event_id": PLACEHOLDER_UUID,
        }
        db_record = _prepare_record(record)
        # Placeholder should NOT appear in db_record at all
        assert "election_event_id" not in db_record

    def test_real_uuid_string_converted_to_uuid_object(self) -> None:
        """A real UUID string for election_event_id should become a uuid.UUID."""
        record = {
            "id": REAL_UUID,
            "name": "Test Election",
            "election_date": "2026-03-10",
            "election_event_id": REAL_UUID,
        }
        db_record = _prepare_record(record)
        assert "election_event_id" in db_record
        assert isinstance(db_record["election_event_id"], uuid.UUID)
        assert db_record["election_event_id"] == uuid.UUID(REAL_UUID)

    def test_none_election_event_id_excluded(self) -> None:
        """None election_event_id should not appear in db_record."""
        record = {
            "id": REAL_UUID,
            "name": "Test Election",
            "election_date": "2026-03-10",
            "election_event_id": None,
        }
        db_record = _prepare_record(record)
        assert "election_event_id" not in db_record
