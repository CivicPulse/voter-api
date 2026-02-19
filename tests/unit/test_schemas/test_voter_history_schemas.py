"""Unit tests for voter history Pydantic schemas."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter_history import (
    BallotStyleBreakdown,
    CountyBreakdown,
    ElectionParticipationRecord,
    PaginatedElectionParticipationResponse,
    PaginatedVoterHistoryResponse,
    ParticipationStatsResponse,
    ParticipationSummary,
    VoterHistoryRecord,
)


class TestVoterHistoryRecord:
    """Tests for VoterHistoryRecord schema."""

    def _make_record(self, **overrides: object) -> VoterHistoryRecord:
        """Create a VoterHistoryRecord with defaults."""
        defaults = {
            "id": uuid4(),
            "voter_registration_number": "12345678",
            "county": "FULTON",
            "election_date": date(2024, 11, 5),
            "election_type": "GENERAL ELECTION",
            "normalized_election_type": "general",
            "absentee": False,
            "provisional": False,
            "supplemental": False,
            "created_at": datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return VoterHistoryRecord(**defaults)

    def test_required_fields(self) -> None:
        """All required fields are accepted."""
        record = self._make_record()
        assert record.voter_registration_number == "12345678"
        assert record.county == "FULTON"
        assert record.election_date == date(2024, 11, 5)
        assert record.election_type == "GENERAL ELECTION"
        assert record.normalized_election_type == "general"
        assert record.absentee is False
        assert record.provisional is False
        assert record.supplemental is False

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None."""
        record = self._make_record()
        assert record.party is None
        assert record.ballot_style is None

    def test_optional_fields_with_values(self) -> None:
        """Optional fields accept values."""
        record = self._make_record(party="NP", ballot_style="BALLOT 1")
        assert record.party == "NP"
        assert record.ballot_style == "BALLOT 1"

    def test_from_attributes_config(self) -> None:
        """Schema has from_attributes enabled."""
        assert VoterHistoryRecord.model_config.get("from_attributes") is True

    def test_missing_required_field_raises(self) -> None:
        """Missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            VoterHistoryRecord(
                id=uuid4(),
                county="FULTON",
                election_date=date(2024, 11, 5),
                election_type="GENERAL ELECTION",
                normalized_election_type="general",
                absentee=False,
                provisional=False,
                supplemental=False,
                created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
                # voter_registration_number missing
            )


class TestElectionParticipationRecord:
    """Tests for ElectionParticipationRecord schema."""

    def _make_record(self, **overrides: object) -> ElectionParticipationRecord:
        """Create an ElectionParticipationRecord with defaults."""
        defaults = {
            "id": uuid4(),
            "voter_registration_number": "12345678",
            "county": "FULTON",
            "election_date": date(2024, 11, 5),
            "election_type": "GENERAL ELECTION",
            "normalized_election_type": "general",
            "absentee": False,
            "provisional": False,
            "supplemental": False,
        }
        defaults.update(overrides)
        return ElectionParticipationRecord(**defaults)

    def test_required_fields(self) -> None:
        """All required fields are accepted."""
        record = self._make_record()
        assert record.voter_registration_number == "12345678"
        assert record.county == "FULTON"

    def test_no_created_at_field(self) -> None:
        """ElectionParticipationRecord does not have created_at."""
        record = self._make_record()
        assert not hasattr(record, "created_at") or "created_at" not in record.model_fields

    def test_from_attributes_config(self) -> None:
        """Schema has from_attributes enabled."""
        assert ElectionParticipationRecord.model_config.get("from_attributes") is True

    def test_optional_fields_default_none(self) -> None:
        """Optional fields default to None."""
        record = self._make_record()
        assert record.party is None
        assert record.ballot_style is None


class TestPaginatedVoterHistoryResponse:
    """Tests for PaginatedVoterHistoryResponse schema."""

    def test_empty_items(self) -> None:
        """Empty items list is valid."""
        resp = PaginatedVoterHistoryResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert resp.items == []
        assert resp.pagination.total == 0

    def test_with_items(self) -> None:
        """Response with items is valid."""
        record = VoterHistoryRecord(
            id=uuid4(),
            voter_registration_number="12345678",
            county="FULTON",
            election_date=date(2024, 11, 5),
            election_type="GENERAL ELECTION",
            normalized_election_type="general",
            absentee=False,
            provisional=False,
            supplemental=False,
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        resp = PaginatedVoterHistoryResponse(
            items=[record],
            pagination=PaginationMeta(total=1, page=1, page_size=20, total_pages=1),
        )
        assert len(resp.items) == 1
        assert resp.pagination.total == 1


class TestPaginatedElectionParticipationResponse:
    """Tests for PaginatedElectionParticipationResponse schema."""

    def test_empty_items(self) -> None:
        """Empty items list is valid."""
        resp = PaginatedElectionParticipationResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        assert resp.items == []


class TestCountyBreakdown:
    """Tests for CountyBreakdown schema."""

    def test_valid_breakdown(self) -> None:
        """County breakdown with name and count."""
        cb = CountyBreakdown(county="FULTON", count=150)
        assert cb.county == "FULTON"
        assert cb.count == 150

    def test_missing_county_raises(self) -> None:
        """Missing county raises ValidationError."""
        with pytest.raises(ValidationError):
            CountyBreakdown(count=10)  # type: ignore[call-arg]


class TestBallotStyleBreakdown:
    """Tests for BallotStyleBreakdown schema."""

    def test_valid_breakdown(self) -> None:
        """Ballot style breakdown with name and count."""
        bs = BallotStyleBreakdown(ballot_style="BALLOT 1", count=75)
        assert bs.ballot_style == "BALLOT 1"
        assert bs.count == 75

    def test_missing_ballot_style_raises(self) -> None:
        """Missing ballot_style raises ValidationError."""
        with pytest.raises(ValidationError):
            BallotStyleBreakdown(count=10)  # type: ignore[call-arg]


class TestParticipationStatsResponse:
    """Tests for ParticipationStatsResponse schema."""

    def test_minimal(self) -> None:
        """Minimal stats with defaults."""
        eid = uuid4()
        stats = ParticipationStatsResponse(election_id=eid, total_participants=100)
        assert stats.election_id == eid
        assert stats.total_participants == 100
        assert stats.by_county == []
        assert stats.by_ballot_style == []

    def test_with_breakdowns(self) -> None:
        """Stats with county and ballot style breakdowns."""
        eid = uuid4()
        stats = ParticipationStatsResponse(
            election_id=eid,
            total_participants=200,
            by_county=[
                CountyBreakdown(county="FULTON", count=120),
                CountyBreakdown(county="DEKALB", count=80),
            ],
            by_ballot_style=[
                BallotStyleBreakdown(ballot_style="STD", count=200),
            ],
        )
        assert len(stats.by_county) == 2
        assert len(stats.by_ballot_style) == 1
        assert stats.by_county[0].county == "FULTON"


class TestParticipationSummary:
    """Tests for ParticipationSummary schema."""

    def test_defaults(self) -> None:
        """Default summary has zero elections and no date."""
        summary = ParticipationSummary()
        assert summary.total_elections == 0
        assert summary.last_election_date is None

    def test_with_values(self) -> None:
        """Summary with populated values."""
        summary = ParticipationSummary(
            total_elections=5,
            last_election_date=date(2024, 11, 5),
        )
        assert summary.total_elections == 5
        assert summary.last_election_date == date(2024, 11, 5)
