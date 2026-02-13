"""Unit tests for address service — backfill_voter_addresses()."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.address_service import backfill_voter_addresses


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    return AsyncMock()


def _make_voter(
    *,
    voter_id: uuid.UUID | None = None,
    street_number: str = "100",
    street_name: str = "MAIN",
    street_type: str = "ST",
    city: str = "ATLANTA",
    zipcode: str = "30303",
) -> MagicMock:
    """Create a mock voter with address components."""
    voter = MagicMock()
    voter.id = voter_id or uuid.uuid4()
    voter.residence_street_number = street_number
    voter.residence_pre_direction = None
    voter.residence_street_name = street_name
    voter.residence_street_type = street_type
    voter.residence_post_direction = None
    voter.residence_apt_unit_number = None
    voter.residence_city = city
    voter.residence_zipcode = zipcode
    voter.residence_address_id = None
    return voter


class TestBackfillVoterAddresses:
    """Tests for backfill_voter_addresses()."""

    @pytest.mark.asyncio
    async def test_no_unlinked_voters(self, mock_session) -> None:
        """Returns zeros when no unlinked voters exist."""
        # Mock count query returns 0
        count_mock = MagicMock()
        count_mock.scalar_one.return_value = 0
        mock_session.execute.return_value = count_mock

        result = await backfill_voter_addresses(mock_session)

        assert result == {"linked": 0, "skipped": 0, "total": 0}

    @pytest.mark.asyncio
    async def test_links_voter_to_address(self, mock_session) -> None:
        """Successfully links voter to canonical address."""
        voter = _make_voter()
        address_mock = MagicMock()
        address_mock.id = uuid.uuid4()

        # First call: count (returns 1)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        # Second call: voter query (returns voter)
        voter_result = MagicMock()
        voter_scalars = MagicMock()
        voter_scalars.all.return_value = [voter]
        voter_result.scalars.return_value = voter_scalars

        mock_session.execute.side_effect = [count_result, voter_result]

        with patch(
            "voter_api.services.address_service.upsert_from_geocode",
            new_callable=AsyncMock,
            return_value=address_mock,
        ):
            result = await backfill_voter_addresses(mock_session, batch_size=100)

        assert result["linked"] == 1
        assert result["skipped"] == 0
        assert voter.residence_address_id == address_mock.id

    @pytest.mark.asyncio
    async def test_skips_voter_without_address_components(self, mock_session) -> None:
        """Skips voters with no reconstructable address."""
        voter = _make_voter(street_number="", street_name="", city="", zipcode="")

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        voter_result = MagicMock()
        voter_scalars = MagicMock()
        voter_scalars.all.return_value = [voter]
        voter_result.scalars.return_value = voter_scalars

        mock_session.execute.side_effect = [count_result, voter_result]

        result = await backfill_voter_addresses(mock_session, batch_size=100)

        assert result["skipped"] == 1
        assert result["linked"] == 0
        assert voter.residence_address_id is None

    @pytest.mark.asyncio
    async def test_is_idempotent(self, mock_session) -> None:
        """Running twice on same data produces same result."""
        # Both runs: no unlinked voters
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        mock_session.execute.return_value = count_result

        result1 = await backfill_voter_addresses(mock_session)
        result2 = await backfill_voter_addresses(mock_session)

        assert result1 == result2 == {"linked": 0, "skipped": 0, "total": 0}
