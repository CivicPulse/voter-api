"""Unit tests for election lifecycle service functions.

Covers:
- US1: Soft-delete (soft_delete_election, get_election_by_id exclusion, list_elections exclusion)
- US2: Manual creation (schema validation, boundary existence check, source field)
- US3: Link (source transition, data_source_url, not-found, wrong-source, duplicate feed)
"""

import uuid
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.schemas.election import ElectionCreateRequest, ElectionLinkRequest
from voter_api.services.election_service import (
    DuplicateElectionError,
    create_election,
    get_election_by_id,
    link_election,
    list_elections,
    soft_delete_election,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_election(**overrides: object) -> MagicMock:
    """Create a mock Election ORM instance."""
    election = MagicMock()
    election.id = uuid.uuid4()
    election.name = "Test Election"
    election.election_date = date(2026, 3, 1)
    election.election_type = "special"
    election.district = "State Senate - District 18"
    election.status = "active"
    election.source = "sos_feed"
    election.data_source_url = "https://results.sos.ga.gov/feed.json"
    election.ballot_item_id = "S18"
    election.boundary_id = None
    election.district_type = None
    election.district_identifier = None
    election.district_party = None
    election.description = None
    election.purpose = None
    election.eligibility_description = None
    election.registration_deadline = None
    election.early_voting_start = None
    election.early_voting_end = None
    election.absentee_request_deadline = None
    election.qualifying_start = None
    election.qualifying_end = None
    election.last_refreshed_at = None
    election.refresh_interval_seconds = 120
    election.deleted_at = None
    election.result = None
    election.created_at = datetime(2026, 2, 1, tzinfo=UTC)
    election.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(election, key, value)
    return election


def _make_scalar_none_session() -> AsyncMock:
    """Session that returns None for scalar_one_or_none."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result
    return session


def _make_scalar_value_session(value: object) -> AsyncMock:
    """Session that returns a specific value for scalar_one_or_none."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# US1: Soft-Delete
# ---------------------------------------------------------------------------


class TestSoftDeleteElection:
    """Tests for soft_delete_election()."""

    @pytest.mark.asyncio
    async def test_soft_delete_election_marks_deleted_at(self) -> None:
        """Calling soft_delete_election sets deleted_at to a non-None timestamp."""
        election = _make_election(deleted_at=None)

        session = AsyncMock()
        session.add = MagicMock()
        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = election
        session.execute.return_value = get_result

        result = await soft_delete_election(session, election.id)

        assert result is True
        assert election.deleted_at is not None
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_election_returns_false_if_not_found(self) -> None:
        """Returns False when the election UUID does not exist."""
        session = _make_scalar_none_session()

        result = await soft_delete_election(session, uuid.uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_get_election_by_id_excludes_deleted(self) -> None:
        """get_election_by_id returns None for soft-deleted elections."""
        # Simulate a deleted election — the service filters deleted_at IS NULL
        # so the query returns no row.
        session = _make_scalar_none_session()

        election = await get_election_by_id(session, uuid.uuid4())

        assert election is None

    @pytest.mark.asyncio
    async def test_list_elections_excludes_deleted(self) -> None:
        """list_elections does not include soft-deleted elections."""
        non_deleted = _make_election(source="sos_feed")

        session = AsyncMock()
        session.add = MagicMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [non_deleted]

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await list_elections(session)

        # Only one election in results — deleted ones would be a second mock
        assert total == 1
        assert len(items) == 1


# ---------------------------------------------------------------------------
# US2: Manual Creation
# ---------------------------------------------------------------------------


class TestCreateElectionManual:
    """Tests for manual election creation schema validation and service behavior."""

    def test_create_election_manual_validates_boundary_required(self) -> None:
        """ElectionCreateRequest with source='manual' and no boundary_id raises ValueError."""
        with pytest.raises(ValueError, match="boundary_id is required for manual elections"):
            ElectionCreateRequest(
                name="Manual Election",
                election_date=date(2026, 5, 1),
                election_type="special",
                district="District 18",
                source="manual",
                boundary_id=None,
            )

    def test_create_election_sos_feed_validates_url_required(self) -> None:
        """ElectionCreateRequest with source='sos_feed' and no data_source_url raises ValueError."""
        with pytest.raises(ValueError, match="data_source_url is required for sos_feed elections"):
            ElectionCreateRequest(
                name="SOS Election",
                election_date=date(2026, 5, 1),
                election_type="special",
                district="District 18",
                source="sos_feed",
                data_source_url=None,
            )

    def test_create_election_manual_no_data_source_url(self) -> None:
        """Manual elections must not have data_source_url."""
        with pytest.raises(ValueError, match="data_source_url must not be set for manual elections"):
            ElectionCreateRequest(
                name="Manual Election",
                election_date=date(2026, 5, 1),
                election_type="special",
                district="District 18",
                source="manual",
                boundary_id=uuid.uuid4(),
                data_source_url="https://example.com/feed.json",
            )

    @pytest.mark.asyncio
    async def test_create_election_manual_validates_boundary_exists(self) -> None:
        """create_election raises ValueError when boundary_id does not exist in DB."""

        boundary_id = uuid.uuid4()
        request = ElectionCreateRequest(
            name="Manual Election",
            election_date=date(2026, 5, 1),
            election_type="special",
            district="District 18",
            source="manual",
            boundary_id=boundary_id,
        )

        # Simulate boundary not found: returns None
        session = AsyncMock()
        session.add = MagicMock()
        session.get = AsyncMock(return_value=None)

        # execute for duplicate check: no election exists
        no_election_result = MagicMock()
        no_election_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=no_election_result)

        with pytest.raises(ValueError, match="[Bb]oundary"):
            await create_election(session, request)

    @pytest.mark.asyncio
    async def test_create_election_manual_sets_source_manual(self) -> None:
        """create_election sets source='manual' on the created election."""
        boundary_id = uuid.uuid4()

        boundary_mock = MagicMock()
        boundary_mock.id = boundary_id

        request = ElectionCreateRequest(
            name="Manual Election",
            election_date=date(2026, 5, 1),
            election_type="special",
            district="District 18",
            source="manual",
            boundary_id=boundary_id,
        )

        created_election = _make_election(source="manual", boundary_id=boundary_id, data_source_url=None)

        # Session: name+date duplicate check (no duplicate), then re-fetch after commit.
        no_duplicate_result = MagicMock()
        no_duplicate_result.scalar_one_or_none.return_value = None

        refetch_result = MagicMock()
        refetch_result.scalar_one.return_value = created_election

        session = AsyncMock()
        session.add = MagicMock()
        session.execute = AsyncMock(side_effect=[no_duplicate_result, refetch_result])
        session.get = AsyncMock(return_value=boundary_mock)

        election = await create_election(session, request)

        assert election.source == "manual"

    @pytest.mark.asyncio
    async def test_create_election_sos_feed_sets_source_sos_feed(self) -> None:
        """create_election sets source='sos_feed' when source field is 'sos_feed'."""
        from unittest.mock import patch

        request = ElectionCreateRequest(
            name="SOS Election",
            election_date=date(2026, 5, 1),
            election_type="special",
            district="District 18",
            source="sos_feed",
            data_source_url="https://results.sos.ga.gov/feed.json",
            ballot_item_id="S18",
        )

        created_election = _make_election(
            source="sos_feed",
            data_source_url="https://results.sos.ga.gov/feed.json",
        )

        # No duplicate by feed+ballot_item, no duplicate by name+date, then re-fetch.
        no_election_result = MagicMock()
        no_election_result.scalar_one_or_none.return_value = None

        refetch_result = MagicMock()
        refetch_result.scalar_one.return_value = created_election

        session = AsyncMock()
        session.add = MagicMock()
        # Three execute calls: feed+ballot_item check, name+date check, selectinload re-fetch.
        session.execute = AsyncMock(side_effect=[no_election_result, no_election_result, refetch_result])

        with patch(
            "voter_api.services.election_resolution_service.link_election_to_boundary",
            new_callable=AsyncMock,
        ):
            election = await create_election(session, request)

        assert election.source == "sos_feed"


# ---------------------------------------------------------------------------
# US3: Link
# ---------------------------------------------------------------------------


class TestLinkElection:
    """Tests for link_election()."""

    @pytest.mark.asyncio
    async def test_link_election_transitions_source_to_linked(self) -> None:
        """link_election sets source='linked' on the election."""
        election = _make_election(source="manual", data_source_url=None)

        session = AsyncMock()
        session.add = MagicMock()

        # get_election_by_id call (returns the manual election)
        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = election

        # Duplicate feed check (no existing linked election with same URL+ballot_item)
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        # Re-fetch after commit with selectinload
        refetch_result = MagicMock()
        refetch_result.scalar_one.return_value = election

        session.execute = AsyncMock(side_effect=[get_result, dup_result, refetch_result])

        request = ElectionLinkRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            ballot_item_id="S18",
        )

        linked = await link_election(session, election.id, request)

        assert linked is not None
        assert linked.source == "linked"

    @pytest.mark.asyncio
    async def test_link_election_sets_data_source_url(self) -> None:
        """link_election sets data_source_url on the election."""
        election = _make_election(source="manual", data_source_url=None)

        session = AsyncMock()
        session.add = MagicMock()

        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = election

        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = None

        # Re-fetch after commit with selectinload
        refetch_result = MagicMock()
        refetch_result.scalar_one.return_value = election

        session.execute = AsyncMock(side_effect=[get_result, dup_result, refetch_result])

        feed_url = "https://results.sos.ga.gov/feed.json"
        request = ElectionLinkRequest(
            data_source_url=feed_url,
            ballot_item_id="S18",
        )

        linked = await link_election(session, election.id, request)

        assert linked is not None
        assert linked.data_source_url == feed_url

    @pytest.mark.asyncio
    async def test_link_election_returns_none_if_not_found(self) -> None:
        """link_election returns None when no election exists for the given UUID."""
        session = _make_scalar_none_session()

        request = ElectionLinkRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
        )

        result = await link_election(session, uuid.uuid4(), request)

        assert result is None

    @pytest.mark.asyncio
    async def test_link_election_raises_value_error_if_not_manual(self) -> None:
        """link_election raises ValueError when the election source is not 'manual'."""
        sos_election = _make_election(source="sos_feed")

        session = AsyncMock()
        session.add = MagicMock()

        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = sos_election

        session.execute = AsyncMock(return_value=get_result)

        request = ElectionLinkRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
        )

        with pytest.raises(ValueError, match="[Mm]anual"):
            await link_election(session, sos_election.id, request)

    @pytest.mark.asyncio
    async def test_link_election_raises_duplicate_error_if_feed_conflict(self) -> None:
        """link_election raises DuplicateElectionError when another election already claims the feed+ballot_item."""
        manual_election = _make_election(source="manual", data_source_url=None)
        already_linked = _make_election(source="linked", data_source_url="https://results.sos.ga.gov/feed.json")

        session = AsyncMock()
        session.add = MagicMock()

        # First call: get_election_by_id returns the manual election
        get_result = MagicMock()
        get_result.scalar_one_or_none.return_value = manual_election

        # Second call: duplicate check finds already_linked election
        dup_result = MagicMock()
        dup_result.scalar_one_or_none.return_value = already_linked

        session.execute = AsyncMock(side_effect=[get_result, dup_result])

        request = ElectionLinkRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            ballot_item_id="S18",
        )

        with pytest.raises(DuplicateElectionError):
            await link_election(session, manual_election.id, request)
