"""Unit tests for election resolution service — PSC county-based resolution."""

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from voter_api.services.election_resolution_service import (
    _resolve_tier2_district_matching,
    _update_vh_by_psc_county,
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
    election.district = "PSC - District 3"
    election.district_type = "psc"
    election.district_identifier = "3"
    election.district_party = None
    election.boundary_id = None
    for key, value in overrides.items():
        setattr(election, key, value)
    return election


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
