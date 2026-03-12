"""Unit tests for election resolution service — PSC county-based + Tier 0 event resolution."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.election_resolution_service import (
    ResolutionResult,
    _resolve_tier0_event_matching,
    _resolve_tier2_district_matching,
    _update_vh_by_psc_county,
    find_or_create_election_event,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_election(**overrides: object) -> MagicMock:
    """Create a mock Election ORM instance with PSC defaults."""
    election = MagicMock()
    election.id = uuid.uuid4()
    election.name = "PSC - District 3"
    election.election_date = date(2024, 11, 5)
    election.election_type = "general"
    election.district = "PSC - District 3"
    election.district_type = "psc"
    election.district_identifier = "3"
    election.district_party = None
    election.boundary_id = None
    election.election_event_id = None
    for key, value in overrides.items():
        setattr(election, key, value)
    return election


# ---------------------------------------------------------------------------
# ResolutionResult
# ---------------------------------------------------------------------------


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_total_updated_includes_tier0(self) -> None:
        """total_updated should include tier0_updated."""
        result = ResolutionResult(tier0_updated=100, tier1_updated=50, tier2_updated=30)
        assert result.total_updated == 180

    def test_total_updated_zero_when_empty(self) -> None:
        """total_updated is 0 when no tiers have updates."""
        result = ResolutionResult()
        assert result.total_updated == 0

    def test_default_tier0_is_zero(self) -> None:
        """tier0_updated defaults to 0."""
        result = ResolutionResult()
        assert result.tier0_updated == 0


# ---------------------------------------------------------------------------
# find_or_create_election_event
# ---------------------------------------------------------------------------


class TestFindOrCreateElectionEvent:
    """Tests for the find_or_create_election_event helper."""

    @pytest.mark.asyncio
    async def test_creates_event_and_returns_id(self) -> None:
        """Creates a new event and returns its UUID."""
        event_id = uuid.uuid4()
        session = AsyncMock()
        # execute is called twice: INSERT, then SELECT
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = event_id
        session.execute.side_effect = [
            MagicMock(),  # INSERT ON CONFLICT DO NOTHING
            scalar_result,  # SELECT id
        ]

        result = await find_or_create_election_event(
            session,
            event_date=date(2024, 11, 5),
            event_type="general",
            event_name="2024 General Election",
        )

        assert result == event_id

    @pytest.mark.asyncio
    async def test_default_event_name(self) -> None:
        """When event_name is None, a default is generated."""
        event_id = uuid.uuid4()
        session = AsyncMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one.return_value = event_id
        session.execute.side_effect = [
            MagicMock(),  # INSERT
            scalar_result,  # SELECT
        ]

        result = await find_or_create_election_event(
            session,
            event_date=date(2024, 11, 5),
            event_type="general",
        )

        assert result == event_id
        # Verify the INSERT was called (first execute call)
        session.execute.assert_called()


# ---------------------------------------------------------------------------
# _resolve_tier0_event_matching
# ---------------------------------------------------------------------------


class TestTier0EventMatching:
    """Tests for Tier 0 event-level resolution."""

    @pytest.mark.asyncio
    @patch(
        "voter_api.services.election_resolution_service._backfill_election_event_ids",
        new_callable=AsyncMock,
    )
    async def test_assigns_event_ids_to_voter_history(self, mock_backfill: AsyncMock) -> None:
        """Tier 0 assigns election_event_id to all matching voter_history records."""
        event_id = uuid.uuid4()

        session = AsyncMock()
        # 1. SELECT DISTINCT (date, type) from voter_history
        date_types_result = MagicMock()
        date_types_result.all.return_value = [(date(2024, 11, 5), "general")]
        # 2. INSERT election_event (find_or_create)
        # 3. SELECT election_event id
        event_select = MagicMock()
        event_select.scalar_one.return_value = event_id
        # 4. UPDATE voter_history SET election_event_id
        update_cursor = MagicMock()
        update_cursor.rowcount = 500

        session.execute.side_effect = [
            date_types_result,  # distinct (date, type)
            MagicMock(),  # INSERT event
            event_select,  # SELECT event id
            update_cursor,  # UPDATE voter_history
        ]

        total = await _resolve_tier0_event_matching(session, force=False)

        assert total == 500
        mock_backfill.assert_awaited_once_with(session)

    @pytest.mark.asyncio
    @patch(
        "voter_api.services.election_resolution_service._backfill_election_event_ids",
        new_callable=AsyncMock,
    )
    async def test_no_records_returns_zero(self, mock_backfill: AsyncMock) -> None:
        """When no voter_history records need resolution, returns 0."""
        session = AsyncMock()
        date_types_result = MagicMock()
        date_types_result.all.return_value = []
        session.execute.return_value = date_types_result

        total = await _resolve_tier0_event_matching(session, force=False)

        assert total == 0
        mock_backfill.assert_not_awaited()

    @pytest.mark.asyncio
    @patch(
        "voter_api.services.election_resolution_service._backfill_election_event_ids",
        new_callable=AsyncMock,
    )
    async def test_multiple_date_type_combinations(self, mock_backfill: AsyncMock) -> None:
        """Tier 0 handles multiple distinct (date, type) combos."""
        event_id_1 = uuid.uuid4()
        event_id_2 = uuid.uuid4()

        session = AsyncMock()

        date_types_result = MagicMock()
        date_types_result.all.return_value = [
            (date(2024, 11, 5), "general"),
            (date(2024, 5, 21), "primary"),
        ]

        event_select_1 = MagicMock()
        event_select_1.scalar_one.return_value = event_id_1
        update_cursor_1 = MagicMock()
        update_cursor_1.rowcount = 300

        event_select_2 = MagicMock()
        event_select_2.scalar_one.return_value = event_id_2
        update_cursor_2 = MagicMock()
        update_cursor_2.rowcount = 200

        session.execute.side_effect = [
            date_types_result,  # distinct combos
            MagicMock(),  # INSERT event 1
            event_select_1,  # SELECT event 1 id
            update_cursor_1,  # UPDATE vh for event 1
            MagicMock(),  # INSERT event 2
            event_select_2,  # SELECT event 2 id
            update_cursor_2,  # UPDATE vh for event 2
        ]

        total = await _resolve_tier0_event_matching(session, force=False)

        assert total == 500
        mock_backfill.assert_awaited_once_with(session)


# ---------------------------------------------------------------------------
# _update_vh_by_psc_county
# ---------------------------------------------------------------------------


class TestUpdateVhByPscCounty:
    """Tests for the _update_vh_by_psc_county helper."""

    @pytest.mark.asyncio
    async def test_updates_matching_county_records(self) -> None:
        """Records with counties in the PSC district list are updated."""
        session = AsyncMock()
        cursor = MagicMock()
        cursor.rowcount = 42
        session.execute.return_value = cursor

        election_id = uuid.uuid4()
        result = await _update_vh_by_psc_county(
            session,
            election_id=election_id,
            election_date=date(2024, 11, 5),
            counties=["DeKalb", "Gwinnett", "Clayton"],
            force=False,
        )

        assert result == 42
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_force_overwrites_existing(self) -> None:
        """When force=True, records with existing election_id are also updated."""
        session = AsyncMock()
        cursor = MagicMock()
        cursor.rowcount = 10
        session.execute.return_value = cursor

        result = await _update_vh_by_psc_county(
            session,
            election_id=uuid.uuid4(),
            election_date=date(2024, 11, 5),
            counties=["Fulton"],
            force=True,
        )

        assert result == 10


# ---------------------------------------------------------------------------
# _resolve_tier2_district_matching — PSC path
# ---------------------------------------------------------------------------


class TestTier2PscResolution:
    """Tests for PSC branch in _resolve_tier2_district_matching."""

    @pytest.mark.asyncio
    async def test_psc_election_resolved_via_county(self) -> None:
        """PSC elections are resolved via county membership instead of voter column."""
        psc_election = _make_election(
            district_type="psc",
            district_identifier="3",
        )

        session = AsyncMock()
        # First call: select elections on date
        elections_result = MagicMock()
        elections_result.scalars.return_value.all.return_value = [psc_election]
        session.execute.side_effect = [
            elections_result,  # SELECT elections
            MagicMock(rowcount=100),  # UPDATE voter_history
        ]

        updated, unresolvable = await _resolve_tier2_district_matching(session, date(2024, 11, 5))

        assert updated == 100
        assert unresolvable == 0

    @pytest.mark.asyncio
    async def test_psc_unknown_district_is_unresolvable(self) -> None:
        """PSC election with invalid district_identifier is marked unresolvable."""
        psc_election = _make_election(
            district_type="psc",
            district_identifier="99",  # Not a real PSC district
        )

        session = AsyncMock()
        elections_result = MagicMock()
        elections_result.scalars.return_value.all.return_value = [psc_election]
        session.execute.return_value = elections_result

        updated, unresolvable = await _resolve_tier2_district_matching(session, date(2024, 11, 5))

        assert updated == 0
        assert unresolvable == 1

    @pytest.mark.asyncio
    async def test_mixed_psc_and_regular_elections(self) -> None:
        """Both PSC (county) and regular (voter column) elections resolve on same date."""
        psc_election = _make_election(
            district_type="psc",
            district_identifier="1",
            name="PSC - District 1",
        )
        senate_election = _make_election(
            district_type="state_senate",
            district_identifier="18",
            name="State Senate - District 18",
        )

        session = AsyncMock()
        elections_result = MagicMock()
        elections_result.scalars.return_value.all.return_value = [
            psc_election,
            senate_election,
        ]

        # Mock: SELECT elections, then PSC county UPDATE, then senate district UPDATE
        psc_cursor = MagicMock(rowcount=50)
        senate_cursor = MagicMock(rowcount=30)
        session.execute.side_effect = [
            elections_result,
            psc_cursor,
            senate_cursor,
        ]

        updated, unresolvable = await _resolve_tier2_district_matching(session, date(2024, 11, 5))

        assert updated == 80
        assert unresolvable == 0
