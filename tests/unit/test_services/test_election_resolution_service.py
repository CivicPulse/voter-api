"""Unit tests for election resolution service — PSC county-based + Tier 0 event resolution."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from voter_api.services.election_resolution_service import (
    ResolutionResult,
    _resolve_tier0_event_matching,
    _resolve_tier1_single_election,
    _resolve_tier2_district_matching,
    _update_vh_by_psc_county,
    find_or_create_election_event,
    link_election_to_boundary,
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


# ---------------------------------------------------------------------------
# _resolve_tier1_single_election — eligible_county priority
# ---------------------------------------------------------------------------


class TestTier1SingleElection:
    """Tests for Tier 1 county scoping with eligible_county priority."""

    async def test_eligible_county_takes_priority_over_boundary(self) -> None:
        """eligible_county is used for county scoping even when boundary.county exists."""
        election_id = uuid.uuid4()
        session = AsyncMock()

        # SELECT returns: (id, district_type, eligible_county, b_county, b_boundary_type, b_name)
        row_result = MagicMock()
        row_result.one.return_value = (
            election_id,
            "county_commission",
            "BIBB",  # eligible_county — should take priority
            "DIFFERENT",  # boundary.county — should be ignored
            "county_commission",
            "Bibb County Commission District 1",
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 11
        session.execute = AsyncMock(side_effect=[row_result, update_cursor])

        updated = await _resolve_tier1_single_election(session, date(2026, 3, 17))

        assert updated == 11
        # Verify the UPDATE includes a county WHERE clause
        update_call = session.execute.call_args_list[1]
        stmt = update_call.args[0]
        stmt_str = str(stmt)
        assert "upper(trim(voter_history.county))" in stmt_str.lower()
        # The bound parameter should be "BIBB" (from eligible_county), not "DIFFERENT"
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        params = compiled.params
        county_param = [v for k, v in params.items() if k.startswith("upper")]
        assert county_param == ["BIBB"]

    async def test_eligible_county_scopes_when_boundary_county_is_null(self) -> None:
        """eligible_county provides county scoping when boundary has no county field."""
        election_id = uuid.uuid4()
        session = AsyncMock()

        row_result = MagicMock()
        row_result.one.return_value = (
            election_id,
            "county_commission",
            "BIBB",  # eligible_county
            None,  # boundary.county is NULL
            "county_commission",
            "Bibb County Commission District 1",
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 11
        session.execute = AsyncMock(side_effect=[row_result, update_cursor])

        updated = await _resolve_tier1_single_election(session, date(2026, 3, 17))

        assert updated == 11
        update_call = session.execute.call_args_list[1]
        stmt = update_call.args[0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        county_param = [v for k, v in compiled.params.items() if k.startswith("upper")]
        assert county_param == ["BIBB"]

    async def test_falls_back_to_boundary_county_when_no_eligible_county(self) -> None:
        """Without eligible_county, boundary.county is used (original behavior)."""
        election_id = uuid.uuid4()
        session = AsyncMock()

        row_result = MagicMock()
        row_result.one.return_value = (
            election_id,
            "state_house",
            None,  # no eligible_county
            "FULTON",  # boundary.county
            "state_house",
            "State House District 55",
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 200
        session.execute = AsyncMock(side_effect=[row_result, update_cursor])

        updated = await _resolve_tier1_single_election(session, date(2024, 11, 5))

        assert updated == 200
        update_call = session.execute.call_args_list[1]
        stmt = update_call.args[0]
        compiled = stmt.compile(compile_kwargs={"literal_binds": False})
        county_param = [v for k, v in compiled.params.items() if k.startswith("upper")]
        assert county_param == ["FULTON"]

    async def test_no_county_scoping_when_all_sources_null(self) -> None:
        """When no county source is available, no county filter is applied."""
        election_id = uuid.uuid4()
        session = AsyncMock()

        row_result = MagicMock()
        row_result.one.return_value = (
            election_id,
            "state_senate",
            None,  # no eligible_county
            None,  # no boundary.county
            "state_senate",
            "State Senate District 18",
        )
        update_cursor = MagicMock()
        update_cursor.rowcount = 500
        session.execute = AsyncMock(side_effect=[row_result, update_cursor])

        updated = await _resolve_tier1_single_election(session, date(2024, 11, 5))

        assert updated == 500
        # No county filter should be in the statement
        update_call = session.execute.call_args_list[1]
        stmt_str = str(update_call.args[0]).lower()
        assert "upper(trim(voter_history.county))" not in stmt_str


# ---------------------------------------------------------------------------
# link_election_to_boundary — eligible_county backfill
# ---------------------------------------------------------------------------


class TestLinkElectionToBoundaryCountyBackfill:
    """Tests for eligible_county backfill in link_election_to_boundary."""

    async def test_sets_eligible_county_from_parsed_district(self) -> None:
        """County commission district text backfills eligible_county."""
        election = _make_election(
            district="Bibb County Commission District 5",
            district_type=None,
            district_identifier=None,
            district_party=None,
            eligible_county=None,
        )

        session = AsyncMock()
        # Boundary lookup: SELECT Boundary.id WHERE ...
        boundary_result = MagicMock()
        boundary_result.first.return_value = None  # no boundary match
        session.execute.return_value = boundary_result

        result = await link_election_to_boundary(session, election)

        assert result is True
        assert election.eligible_county == "BIBB"
        assert election.district_type == "county_commission"
        assert election.district_identifier == "5"

    async def test_does_not_overwrite_existing_eligible_county(self) -> None:
        """Preserves eligible_county set by candidate import (more authoritative)."""
        election = _make_election(
            district="Bibb County Commission District 5",
            district_type=None,
            district_identifier=None,
            district_party=None,
            eligible_county="HOUSTON",  # already set by candidate import
        )

        session = AsyncMock()
        boundary_result = MagicMock()
        boundary_result.first.return_value = None
        session.execute.return_value = boundary_result

        result = await link_election_to_boundary(session, election)

        assert result is True
        assert election.eligible_county == "HOUSTON"  # preserved, not overwritten

    async def test_no_county_backfill_for_non_county_district(self) -> None:
        """Non-county districts (e.g. state_senate) don't set eligible_county."""
        election = _make_election(
            district="State Senate District 18",
            district_type=None,
            district_identifier=None,
            district_party=None,
            eligible_county=None,
        )

        session = AsyncMock()
        boundary_result = MagicMock()
        boundary_result.first.return_value = None
        session.execute.return_value = boundary_result

        result = await link_election_to_boundary(session, election)

        assert result is True
        assert election.eligible_county is None  # no county to extract
