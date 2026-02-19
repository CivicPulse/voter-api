"""Contract tests validating voter history Pydantic schemas match OpenAPI spec.

Covers T038: verify response schemas for all 4 voter history endpoints
produce valid JSON-serializable output matching contracts/openapi.yaml.
"""

import uuid
from datetime import UTC, date, datetime

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


class TestVoterHistoryRecordContract:
    """VoterHistoryRecord matches OpenAPI VoterHistoryRecord schema."""

    def test_all_fields_serializable(self) -> None:
        """All fields serialize to JSON-compatible types."""
        record = VoterHistoryRecord(
            id=uuid.uuid4(),
            voter_registration_number="12345678",
            county="FULTON",
            election_date=date(2024, 11, 5),
            election_type="GENERAL ELECTION",
            normalized_election_type="general",
            party="NP",
            ballot_style="BALLOT 1",
            absentee=True,
            provisional=False,
            supplemental=False,
            created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        data = record.model_dump(mode="json")
        assert isinstance(data["id"], str)
        assert isinstance(data["election_date"], str)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["absentee"], bool)

    def test_nullable_fields(self) -> None:
        """Nullable fields serialize as null when absent."""
        record = VoterHistoryRecord(
            id=uuid.uuid4(),
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
        data = record.model_dump(mode="json")
        assert data["party"] is None
        assert data["ballot_style"] is None


class TestPaginatedVoterHistoryResponseContract:
    """GET /voters/{reg_num}/history response contract."""

    def test_response_structure(self) -> None:
        """Response has items array and pagination object."""
        resp = PaginatedVoterHistoryResponse(
            items=[
                VoterHistoryRecord(
                    id=uuid.uuid4(),
                    voter_registration_number="12345678",
                    county="FULTON",
                    election_date=date(2024, 11, 5),
                    election_type="GENERAL ELECTION",
                    normalized_election_type="general",
                    absentee=False,
                    provisional=False,
                    supplemental=False,
                    created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
                ),
            ],
            pagination=PaginationMeta(total=1, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)
        assert data["pagination"]["total"] == 1
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 20
        assert data["pagination"]["total_pages"] == 1

    def test_empty_response(self) -> None:
        """Empty response is valid with zero total."""
        resp = PaginatedVoterHistoryResponse(
            items=[],
            pagination=PaginationMeta(total=0, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert data["items"] == []
        assert data["pagination"]["total"] == 0


class TestElectionParticipationRecordContract:
    """ElectionParticipationRecord matches OpenAPI schema."""

    def test_all_fields_serializable(self) -> None:
        """All fields serialize to JSON-compatible types."""
        record = ElectionParticipationRecord(
            id=uuid.uuid4(),
            voter_registration_number="12345678",
            county="DEKALB",
            election_date=date(2024, 5, 21),
            election_type="GENERAL PRIMARY",
            normalized_election_type="primary",
            party="DEM",
            ballot_style="STD",
            absentee=True,
            provisional=False,
            supplemental=False,
        )
        data = record.model_dump(mode="json")
        assert isinstance(data["id"], str)
        assert data["county"] == "DEKALB"
        assert data["normalized_election_type"] == "primary"

    def test_no_created_at(self) -> None:
        """ElectionParticipationRecord does not include created_at."""
        record = ElectionParticipationRecord(
            id=uuid.uuid4(),
            voter_registration_number="12345678",
            county="FULTON",
            election_date=date(2024, 11, 5),
            election_type="GENERAL ELECTION",
            normalized_election_type="general",
            absentee=False,
            provisional=False,
            supplemental=False,
        )
        data = record.model_dump(mode="json")
        assert "created_at" not in data


class TestPaginatedElectionParticipationResponseContract:
    """GET /elections/{id}/participation response contract."""

    def test_response_structure(self) -> None:
        """Response has items array and pagination object."""
        resp = PaginatedElectionParticipationResponse(
            items=[
                ElectionParticipationRecord(
                    id=uuid.uuid4(),
                    voter_registration_number="12345678",
                    county="FULTON",
                    election_date=date(2024, 11, 5),
                    election_type="GENERAL ELECTION",
                    normalized_election_type="general",
                    absentee=False,
                    provisional=False,
                    supplemental=False,
                ),
            ],
            pagination=PaginationMeta(total=1, page=1, page_size=20, total_pages=1),
        )
        data = resp.model_dump(mode="json")
        assert "items" in data
        assert "pagination" in data
        assert len(data["items"]) == 1


class TestParticipationStatsResponseContract:
    """GET /elections/{id}/participation/stats response contract."""

    def test_full_response(self) -> None:
        """Full stats response with breakdowns."""
        eid = uuid.uuid4()
        resp = ParticipationStatsResponse(
            election_id=eid,
            total_participants=500,
            by_county=[
                CountyBreakdown(county="FULTON", count=300),
                CountyBreakdown(county="DEKALB", count=200),
            ],
            by_ballot_style=[
                BallotStyleBreakdown(ballot_style="STD", count=400),
                BallotStyleBreakdown(ballot_style="ABSENTEE", count=100),
            ],
        )
        data = resp.model_dump(mode="json")
        assert isinstance(data["election_id"], str)
        assert data["total_participants"] == 500
        assert len(data["by_county"]) == 2
        assert data["by_county"][0]["county"] == "FULTON"
        assert data["by_county"][0]["count"] == 300
        assert len(data["by_ballot_style"]) == 2

    def test_empty_breakdowns(self) -> None:
        """Empty breakdowns default to empty lists."""
        resp = ParticipationStatsResponse(
            election_id=uuid.uuid4(),
            total_participants=0,
        )
        data = resp.model_dump(mode="json")
        assert data["by_county"] == []
        assert data["by_ballot_style"] == []


class TestParticipationSummaryContract:
    """ParticipationSummary in voter detail response contract."""

    def test_default_values(self) -> None:
        """Default summary serializes with zero/null."""
        summary = ParticipationSummary()
        data = summary.model_dump(mode="json")
        assert data["total_elections"] == 0
        assert data["last_election_date"] is None

    def test_with_data(self) -> None:
        """Summary with data serializes correctly."""
        summary = ParticipationSummary(
            total_elections=12,
            last_election_date=date(2024, 11, 5),
        )
        data = summary.model_dump(mode="json")
        assert data["total_elections"] == 12
        assert data["last_election_date"] == "2024-11-05"
