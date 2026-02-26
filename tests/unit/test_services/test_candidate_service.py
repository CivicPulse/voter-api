"""Unit tests for the candidate service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from voter_api.schemas.candidate import (
    CandidateCreateRequest,
    CandidateDetailResponse,
    CandidateLinkCreateRequest,
    CandidateLinkResponse,
    CandidateUpdateRequest,
    FilingStatus,
    LinkType,
)
from voter_api.services.candidate_service import (
    _UPDATABLE_FIELDS,
    add_candidate_link,
    build_candidate_detail_response,
    create_candidate,
    delete_candidate,
    delete_candidate_link,
    get_candidate,
    get_candidate_with_results,
    list_candidates,
    update_candidate,
)

# --- Helpers ---


def _mock_candidate_link(**overrides: object) -> MagicMock:
    """Create a mock CandidateLink ORM instance."""
    link = MagicMock()
    link.id = uuid.uuid4()
    link.candidate_id = uuid.uuid4()
    link.link_type = "website"
    link.url = "https://example.com"
    link.label = "Campaign Site"
    link.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(link, key, value)
    return link


def _mock_candidate(**overrides: object) -> MagicMock:
    """Create a mock Candidate ORM instance."""
    candidate = MagicMock()
    candidate.id = uuid.uuid4()
    candidate.election_id = uuid.uuid4()
    candidate.full_name = "Jane Doe"
    candidate.party = "Dem"
    candidate.bio = "A great candidate."
    candidate.photo_url = "https://example.com/photo.jpg"
    candidate.ballot_order = 1
    candidate.filing_status = "qualified"
    candidate.is_incumbent = False
    candidate.sos_ballot_option_id = None
    candidate.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    candidate.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    candidate.links = []
    for key, value in overrides.items():
        setattr(candidate, key, value)
    return candidate


def _mock_session_with_scalar(scalar_result: object) -> AsyncMock:
    """Create mock session returning a specific scalar_one_or_none result."""
    session = AsyncMock()
    # session.add is synchronous on AsyncSession; use MagicMock to avoid
    # "coroutine was never awaited" warnings.
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_result
    session.execute.return_value = result
    return session


# --- Tests for list_candidates ---


class TestListCandidates:
    """Tests for list_candidates()."""

    @pytest.mark.asyncio
    async def test_empty_result(self):
        """Returns empty list and zero total when no candidates exist."""
        # First execute: count query returns 0
        count_mock = MagicMock()
        count_mock.scalar_one.return_value = 0

        # Second execute: list query returns empty
        list_mock = MagicMock()
        list_mock.scalars.return_value.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[count_mock, list_mock])

        election_id = uuid.uuid4()
        candidates, total = await list_candidates(session, election_id)

        assert candidates == []
        assert total == 0
        assert session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_with_results_and_pagination(self):
        """Returns candidates with correct total for pagination."""
        c1 = _mock_candidate(full_name="Alice", ballot_order=1)
        c2 = _mock_candidate(full_name="Bob", ballot_order=2)

        count_mock = MagicMock()
        count_mock.scalar_one.return_value = 5  # total across all pages

        list_mock = MagicMock()
        list_mock.scalars.return_value.all.return_value = [c1, c2]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[count_mock, list_mock])

        election_id = uuid.uuid4()
        candidates, total = await list_candidates(session, election_id, page=1, page_size=2)

        assert len(candidates) == 2
        assert total == 5
        assert candidates[0] is c1
        assert candidates[1] is c2

    @pytest.mark.asyncio
    async def test_status_filter(self):
        """Filters candidates by filing status."""
        c1 = _mock_candidate(filing_status="withdrawn")

        count_mock = MagicMock()
        count_mock.scalar_one.return_value = 1

        list_mock = MagicMock()
        list_mock.scalars.return_value.all.return_value = [c1]

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[count_mock, list_mock])

        election_id = uuid.uuid4()
        candidates, total = await list_candidates(session, election_id, status="withdrawn")

        assert len(candidates) == 1
        assert total == 1
        assert candidates[0].filing_status == "withdrawn"


# --- Tests for get_candidate ---


class TestGetCandidate:
    """Tests for get_candidate()."""

    @pytest.mark.asyncio
    async def test_found(self):
        """Returns candidate when found."""
        candidate = _mock_candidate()
        session = _mock_session_with_scalar(candidate)

        result = await get_candidate(session, candidate.id)

        assert result is candidate
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns None when candidate does not exist."""
        session = _mock_session_with_scalar(None)

        result = await get_candidate(session, uuid.uuid4())

        assert result is None


# --- Tests for create_candidate ---


class TestCreateCandidate:
    """Tests for create_candidate()."""

    @pytest.mark.asyncio
    async def test_creates_without_links(self):
        """Creates a candidate with no initial links."""
        mock_candidate = _mock_candidate()

        # After flush+commit, re-fetch returns the candidate
        refetch_mock = MagicMock()
        refetch_mock.scalar_one.return_value = mock_candidate

        session = AsyncMock()
        session.add = MagicMock()  # synchronous on AsyncSession
        session.execute = AsyncMock(return_value=refetch_mock)

        request = CandidateCreateRequest(
            full_name="Jane Doe",
            party="Dem",
            filing_status=FilingStatus.QUALIFIED,
        )

        election_id = uuid.uuid4()
        result = await create_candidate(session, election_id, request)

        assert result is mock_candidate
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_with_links(self):
        """Creates a candidate with initial links."""
        link = _mock_candidate_link()
        mock_candidate = _mock_candidate(links=[link])

        refetch_mock = MagicMock()
        refetch_mock.scalar_one.return_value = mock_candidate

        session = AsyncMock()
        session.add = MagicMock()  # synchronous on AsyncSession
        session.execute = AsyncMock(return_value=refetch_mock)

        request = CandidateCreateRequest(
            full_name="Jane Doe",
            party="Dem",
            links=[
                CandidateLinkCreateRequest(
                    link_type=LinkType.WEBSITE,
                    url="https://example.com",
                    label="Campaign Site",
                ),
            ],
        )

        election_id = uuid.uuid4()
        result = await create_candidate(session, election_id, request)

        assert result is mock_candidate
        # One for candidate, one for the link
        assert session.add.call_count == 2
        session.flush.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_raises_value_error(self):
        """Raises ValueError when candidate name conflicts."""
        session = AsyncMock()
        session.add = MagicMock()  # synchronous on AsyncSession
        session.flush.side_effect = IntegrityError("INSERT", {}, Exception("duplicate key"))

        request = CandidateCreateRequest(
            full_name="Jane Doe",
            party="Dem",
        )

        with pytest.raises(ValueError, match="already exists"):
            await create_candidate(session, uuid.uuid4(), request)

        session.rollback.assert_awaited_once()


# --- Tests for update_candidate ---


class TestUpdateCandidate:
    """Tests for update_candidate()."""

    @pytest.mark.asyncio
    async def test_partial_update(self):
        """Applies partial update to allowed fields."""
        candidate = _mock_candidate(full_name="Jane Doe", party="Dem")
        session = _mock_session_with_scalar(candidate)

        request = CandidateUpdateRequest(party="Rep", is_incumbent=True)
        result = await update_candidate(session, candidate.id, request)

        assert result is candidate
        assert candidate.party == "Rep"
        assert candidate.is_incumbent is True
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once_with(candidate)

    @pytest.mark.asyncio
    async def test_nonexistent_returns_none(self):
        """Returns None if candidate not found."""
        session = _mock_session_with_scalar(None)

        request = CandidateUpdateRequest(party="Rep")
        result = await update_candidate(session, uuid.uuid4(), request)

        assert result is None
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_allowlist_enforcement(self):
        """Only _UPDATABLE_FIELDS are applied; other fields are ignored."""
        candidate = _mock_candidate()
        original_election_id = candidate.election_id

        session = _mock_session_with_scalar(candidate)

        # Construct a request with an allowed field and verify non-updatable
        # fields in the model aren't in the allowlist
        request = CandidateUpdateRequest(full_name="Updated Name")
        result = await update_candidate(session, candidate.id, request)

        assert result is candidate
        assert candidate.full_name == "Updated Name"
        # election_id is not in _UPDATABLE_FIELDS and should be unchanged
        assert candidate.election_id == original_election_id

    @pytest.mark.asyncio
    async def test_filing_status_enum_conversion(self):
        """Filing status string is converted through FilingStatus enum."""
        candidate = _mock_candidate(filing_status="qualified")
        session = _mock_session_with_scalar(candidate)

        request = CandidateUpdateRequest(filing_status=FilingStatus.WITHDRAWN)
        result = await update_candidate(session, candidate.id, request)

        assert result is candidate
        assert candidate.filing_status == "withdrawn"

    @pytest.mark.asyncio
    async def test_integrity_error_raises_value_error(self):
        """Raises ValueError on name conflict during update."""
        candidate = _mock_candidate()
        session = _mock_session_with_scalar(candidate)
        session.commit.side_effect = IntegrityError("UPDATE", {}, Exception("duplicate key"))

        request = CandidateUpdateRequest(full_name="Existing Name")

        with pytest.raises(ValueError, match="already exists"):
            await update_candidate(session, candidate.id, request)

        session.rollback.assert_awaited_once()


# --- Tests for delete_candidate ---


class TestDeleteCandidate:
    """Tests for delete_candidate()."""

    @pytest.mark.asyncio
    async def test_deletes_existing(self):
        """Returns True when candidate is found and deleted."""
        candidate = _mock_candidate()
        session = _mock_session_with_scalar(candidate)

        result = await delete_candidate(session, candidate.id)

        assert result is True
        session.delete.assert_awaited_once_with(candidate)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns False when candidate does not exist."""
        session = _mock_session_with_scalar(None)

        result = await delete_candidate(session, uuid.uuid4())

        assert result is False
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()


# --- Tests for add_candidate_link ---


class TestAddCandidateLink:
    """Tests for add_candidate_link()."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Adds a link to an existing candidate."""
        candidate = _mock_candidate()
        session = _mock_session_with_scalar(candidate)

        request = CandidateLinkCreateRequest(
            link_type=LinkType.TWITTER,
            url="https://twitter.com/janedoe",
            label="Twitter",
        )

        result = await add_candidate_link(session, candidate.id, request)

        assert result is not None
        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_nonexistent_candidate(self):
        """Returns None when candidate does not exist."""
        session = _mock_session_with_scalar(None)

        request = CandidateLinkCreateRequest(
            link_type=LinkType.WEBSITE,
            url="https://example.com",
        )

        result = await add_candidate_link(session, uuid.uuid4(), request)

        assert result is None
        session.add.assert_not_called()
        session.commit.assert_not_awaited()


# --- Tests for delete_candidate_link ---


class TestDeleteCandidateLink:
    """Tests for delete_candidate_link()."""

    @pytest.mark.asyncio
    async def test_success(self):
        """Deletes link that belongs to the specified candidate."""
        link = _mock_candidate_link()
        session = _mock_session_with_scalar(link)

        result = await delete_candidate_link(session, link.candidate_id, link.id)

        assert result is True
        session.delete.assert_awaited_once_with(link)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrong_candidate(self):
        """Returns False when link exists but belongs to different candidate."""
        # The query filters on both link_id and candidate_id, so a wrong
        # candidate_id means scalar_one_or_none returns None.
        session = _mock_session_with_scalar(None)

        result = await delete_candidate_link(session, uuid.uuid4(), uuid.uuid4())

        assert result is False
        session.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_not_found(self):
        """Returns False when link does not exist."""
        session = _mock_session_with_scalar(None)

        result = await delete_candidate_link(session, uuid.uuid4(), uuid.uuid4())

        assert result is False
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()


# --- Tests for build_candidate_detail_response ---


class TestBuildCandidateDetailResponse:
    """Tests for build_candidate_detail_response()."""

    def test_builds_response_without_results(self):
        """Builds detail response with no SOS result data."""
        candidate = _mock_candidate()
        response = build_candidate_detail_response(candidate)

        assert isinstance(response, CandidateDetailResponse)
        assert response.id == candidate.id
        assert response.election_id == candidate.election_id
        assert response.full_name == "Jane Doe"
        assert response.party == "Dem"
        assert response.filing_status == "qualified"
        assert response.result_vote_count is None
        assert response.result_political_party is None
        assert response.links == []

    def test_builds_response_with_results(self):
        """Includes vote count and party when provided."""
        candidate = _mock_candidate()
        response = build_candidate_detail_response(
            candidate,
            result_vote_count=1500,
            result_political_party="Dem",
        )

        assert response.result_vote_count == 1500
        assert response.result_political_party == "Dem"

    def test_builds_response_with_links(self):
        """Includes candidate links in the response."""
        link = _mock_candidate_link()
        candidate = _mock_candidate(links=[link])
        response = build_candidate_detail_response(candidate)

        assert len(response.links) == 1
        assert isinstance(response.links[0], CandidateLinkResponse)
        assert response.links[0].id == link.id
        assert response.links[0].url == link.url
        assert response.links[0].link_type == link.link_type


# --- Tests for get_candidate_with_results ---


class TestGetCandidateWithResults:
    """Tests for get_candidate_with_results()."""

    @pytest.mark.asyncio
    async def test_with_sos_match(self):
        """Returns enriched response when SOS result matches."""
        sos_id = "ballot-opt-42"
        candidate = _mock_candidate(sos_ballot_option_id=sos_id)

        election_result = MagicMock()
        election_result.results_data = [
            {
                "id": sos_id,
                "name": "Jane Doe",
                "politicalParty": "Dem",
                "voteCount": 2500,
            },
            {
                "id": "other-id",
                "name": "Other",
                "politicalParty": "Rep",
                "voteCount": 1000,
            },
        ]

        # First execute: get_candidate returns the candidate
        candidate_result_mock = MagicMock()
        candidate_result_mock.scalar_one_or_none.return_value = candidate

        # Second execute: ElectionResult query
        er_result_mock = MagicMock()
        er_result_mock.scalar_one_or_none.return_value = election_result

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[candidate_result_mock, er_result_mock])

        result = await get_candidate_with_results(session, candidate.id)

        assert result is not None
        assert isinstance(result, CandidateDetailResponse)
        assert result.result_vote_count == 2500
        assert result.result_political_party == "Dem"

    @pytest.mark.asyncio
    async def test_without_sos_match(self):
        """Returns response without results when SOS ID doesn't match."""
        candidate = _mock_candidate(sos_ballot_option_id="no-match")

        election_result = MagicMock()
        election_result.results_data = [
            {
                "id": "different-id",
                "name": "Other",
                "politicalParty": "Rep",
                "voteCount": 500,
            },
        ]

        candidate_result_mock = MagicMock()
        candidate_result_mock.scalar_one_or_none.return_value = candidate

        er_result_mock = MagicMock()
        er_result_mock.scalar_one_or_none.return_value = election_result

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[candidate_result_mock, er_result_mock])

        result = await get_candidate_with_results(session, candidate.id)

        assert result is not None
        assert result.result_vote_count is None
        assert result.result_political_party is None

    @pytest.mark.asyncio
    async def test_no_result_data(self):
        """Returns response without results when no ElectionResult exists."""
        candidate = _mock_candidate(sos_ballot_option_id="some-id")

        candidate_result_mock = MagicMock()
        candidate_result_mock.scalar_one_or_none.return_value = candidate

        # No election result found
        er_result_mock = MagicMock()
        er_result_mock.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[candidate_result_mock, er_result_mock])

        result = await get_candidate_with_results(session, candidate.id)

        assert result is not None
        assert result.result_vote_count is None
        assert result.result_political_party is None

    @pytest.mark.asyncio
    async def test_no_sos_ballot_option_id(self):
        """Skips SOS lookup when candidate has no sos_ballot_option_id."""
        candidate = _mock_candidate(sos_ballot_option_id=None)

        session = _mock_session_with_scalar(candidate)

        result = await get_candidate_with_results(session, candidate.id)

        assert result is not None
        assert result.result_vote_count is None
        assert result.result_political_party is None
        # Only one execute call for get_candidate; no ElectionResult query
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_candidate_not_found(self):
        """Returns None when candidate does not exist."""
        session = _mock_session_with_scalar(None)

        result = await get_candidate_with_results(session, uuid.uuid4())

        assert result is None


# --- Tests for _UPDATABLE_FIELDS constant ---


class TestUpdatableFields:
    """Verify the allowlist constant is correct."""

    def test_expected_fields(self):
        """_UPDATABLE_FIELDS contains exactly the expected set."""
        expected = frozenset(
            {
                "full_name",
                "party",
                "bio",
                "photo_url",
                "ballot_order",
                "filing_status",
                "is_incumbent",
                "sos_ballot_option_id",
            }
        )
        assert expected == _UPDATABLE_FIELDS

    def test_is_frozenset(self):
        """_UPDATABLE_FIELDS is immutable."""
        assert isinstance(_UPDATABLE_FIELDS, frozenset)
