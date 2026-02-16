"""Unit tests for feed import service functions."""

import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import time_machine

from voter_api.lib.election_tracker.parser import (
    BallotItem,
    BallotOption,
    SoSFeed,
    SoSResults,
)
from voter_api.schemas.election import (
    FeedImportPreviewResponse,
    FeedImportRequest,
    FeedImportResponse,
)
from voter_api.services.election_service import (
    DuplicateElectionError,
    import_feed,
    preview_feed_import,
)


def _mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.election_allowed_domain_list = ["results.sos.ga.gov"]
    return settings


def _mock_election(ballot_item_id: str) -> MagicMock:
    """Create a mock Election returned by create_election."""
    election = MagicMock()
    election.id = uuid.uuid4()
    election.ballot_item_id = ballot_item_id
    return election


def _make_multi_race_feed() -> SoSFeed:
    return SoSFeed(
        electionDate="2025-11-04",
        electionName="November 4, 2025 - Multi-Race Election",
        createdAt="2025-11-04T20:00:00Z",
        results=SoSResults(
            id="GA",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="S10",
                    name="PSC - District 2",
                    precinctsParticipating=4000,
                    precinctsReporting=3500,
                    ballotOptions=[
                        BallotOption(id="c1", name="Tim Echols", voteCount=582402, politicalParty="Rep"),
                        BallotOption(id="c2", name="Alicia Johnson", voteCount=980471, politicalParty="Dem"),
                    ],
                ),
                BallotItem(
                    id="S11",
                    name="PSC - District 3",
                    precinctsParticipating=4000,
                    precinctsReporting=3600,
                    ballotOptions=[
                        BallotOption(id="c3", name="Fitz Johnson", voteCount=578476, politicalParty="Rep"),
                    ],
                ),
            ],
        ),
        localResults=[],
    )


def _make_recent_feed() -> SoSFeed:
    """Build a multi-race feed with a recent date (within 14 days) so status='active'."""
    recent_date = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    return SoSFeed(
        electionDate=recent_date,
        electionName="February Special Election",
        createdAt="2026-02-13T20:00:00Z",
        results=SoSResults(
            id="GA",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="S10",
                    name="PSC - District 2",
                    precinctsParticipating=4000,
                    precinctsReporting=3500,
                    ballotOptions=[
                        BallotOption(id="c1", name="Tim Echols", voteCount=582402, politicalParty="Rep"),
                        BallotOption(id="c2", name="Alicia Johnson", voteCount=980471, politicalParty="Dem"),
                    ],
                ),
                BallotItem(
                    id="S11",
                    name="PSC - District 3",
                    precinctsParticipating=4000,
                    precinctsReporting=3600,
                    ballotOptions=[
                        BallotOption(id="c3", name="Fitz Johnson", voteCount=578476, politicalParty="Rep"),
                    ],
                ),
            ],
        ),
        localResults=[],
    )


def _make_boundary_feed(days_ago: int) -> SoSFeed:
    """Build a feed with electionDate exactly `days_ago` days before today."""
    boundary_date = (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()
    return SoSFeed(
        electionDate=boundary_date,
        electionName="Boundary Test Election",
        createdAt="2026-01-01T00:00:00Z",
        results=SoSResults(
            id="GA",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="S10",
                    name="PSC - District 2",
                    precinctsParticipating=4000,
                    precinctsReporting=3500,
                    ballotOptions=[
                        BallotOption(id="c1", name="Candidate A", voteCount=100, politicalParty="Rep"),
                    ],
                ),
            ],
        ),
        localResults=[],
    )


def _make_general_feed() -> SoSFeed:
    """Build a feed with 'General' in the electionName for keyword detection tests."""
    recent_date = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    return SoSFeed(
        electionDate=recent_date,
        electionName="November General Election",
        createdAt="2026-01-01T00:00:00Z",
        results=SoSResults(
            id="GA",
            name="Georgia",
            ballotItems=[
                BallotItem(
                    id="S10",
                    name="PSC - District 2",
                    precinctsParticipating=4000,
                    precinctsReporting=3500,
                    ballotOptions=[
                        BallotOption(id="c1", name="Candidate A", voteCount=100, politicalParty="Rep"),
                        BallotOption(id="c2", name="Candidate B", voteCount=200, politicalParty="Dem"),
                    ],
                ),
            ],
        ),
        localResults=[],
    )


def _make_empty_feed() -> SoSFeed:
    return SoSFeed(
        electionDate="2025-11-04",
        electionName="Empty Election",
        createdAt="2025-11-04T20:00:00Z",
        results=SoSResults(id="GA", name="Georgia", ballotItems=[]),
        localResults=[],
    )


class TestPreviewFeedImport:
    """Tests for preview_feed_import()."""

    @pytest.mark.asyncio
    async def test_returns_preview_with_races(self):
        feed = _make_multi_race_feed()

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
        ):
            result = await preview_feed_import("https://results.sos.ga.gov/feed.json")

        assert isinstance(result, FeedImportPreviewResponse)
        assert result.total_races == 2
        assert result.election_date == date(2025, 11, 4)
        assert result.election_name == "November 4, 2025 - Multi-Race Election"
        assert result.detected_election_type == "special"
        assert result.races[0].ballot_item_id == "S10"
        assert result.races[0].name == "PSC - District 2"
        assert result.races[0].candidate_count == 2
        assert result.races[1].ballot_item_id == "S11"
        assert result.races[1].candidate_count == 1

    @pytest.mark.asyncio
    async def test_preview_empty_feed(self):
        feed = _make_empty_feed()

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
        ):
            result = await preview_feed_import("https://results.sos.ga.gov/feed.json")

        assert result.total_races == 0
        assert result.races == []

    @pytest.mark.asyncio
    async def test_preview_detects_general_from_feed_name(self):
        """Preview auto-detects 'general' when feed name contains the keyword."""
        feed = _make_general_feed()

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
        ):
            result = await preview_feed_import("https://results.sos.ga.gov/feed.json")

        assert result.detected_election_type == "general"


class TestImportFeed:
    """Tests for import_feed()."""

    @pytest.mark.asyncio
    async def test_creates_election_per_race(self):
        feed = _make_multi_race_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            result = await import_feed(session, request)

        assert isinstance(result, FeedImportResponse)
        assert result.elections_created == 2
        assert result.elections[0].ballot_item_id == "S10"
        assert result.elections[0].name == "November 4, 2025 - Multi-Race Election - PSC - District 2"
        assert result.elections[1].ballot_item_id == "S11"
        assert result.elections[0].refreshed is False
        assert mock_create.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_on_empty_feed(self):
        feed = _make_empty_feed()
        session = AsyncMock()

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            pytest.raises(ValueError, match="no ballot items"),
        ):
            await import_feed(session, request)

    @pytest.mark.asyncio
    async def test_skips_duplicates(self):
        feed = _make_multi_race_feed()
        session = AsyncMock()

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=DuplicateElectionError("already exists"),
            ),
        ):
            result = await import_feed(session, request)

        assert result.elections_created == 0
        assert result.elections == []

    @pytest.mark.asyncio
    @time_machine.travel("2026-02-16", tick=False)
    async def test_auto_refresh_calls_refresh(self):
        """Auto-refresh runs for active (recent) elections."""
        feed = _make_recent_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=True,
        )

        mock_refresh_response = MagicMock()
        mock_refresh_response.precincts_reporting = 3500
        mock_refresh_response.precincts_participating = 4000

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ),
            patch(
                "voter_api.services.election_service.refresh_single_election",
                new_callable=AsyncMock,
                return_value=mock_refresh_response,
            ) as mock_refresh,
        ):
            result = await import_feed(session, request)

        assert mock_refresh.await_count == 2
        assert result.elections[0].refreshed is True
        assert result.elections[0].precincts_reporting == 3500
        assert result.elections[0].status == "active"

    @pytest.mark.asyncio
    async def test_election_name_format(self):
        """Verify auto-generated election names combine feed name + race name."""
        feed = _make_multi_race_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ),
        ):
            result = await import_feed(session, request)

        assert "PSC - District 2" in result.elections[0].name
        assert "PSC - District 3" in result.elections[1].name
        assert result.elections[0].election_date == date(2025, 11, 4)

    @pytest.mark.asyncio
    async def test_auto_refresh_failure_still_includes_election(self):
        """If auto-refresh fails, the election is still included with refreshed=False."""
        feed = _make_recent_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=True,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ),
            patch(
                "voter_api.services.election_service.refresh_single_election",
                new_callable=AsyncMock,
                side_effect=ValueError("refresh failed"),
            ),
        ):
            result = await import_feed(session, request)

        assert result.elections_created == 2
        assert result.elections[0].refreshed is False
        assert result.elections[0].precincts_reporting is None
        assert result.elections[1].refreshed is False

    @pytest.mark.asyncio
    async def test_skips_duplicates_tracks_count(self):
        """Duplicate elections are counted in elections_skipped."""
        feed = _make_multi_race_feed()
        session = AsyncMock()

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=DuplicateElectionError("already exists"),
            ),
        ):
            result = await import_feed(session, request)

        assert result.elections_created == 0
        assert result.elections_skipped == 2
        assert result.elections == []

    @pytest.mark.asyncio
    async def test_auto_detect_type_when_none(self):
        """When election_type is None, type is auto-detected from feed name."""
        feed = _make_multi_race_feed()  # electionName contains no keyword → "special"
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type=None,
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            await import_feed(session, request)

        # election_type should be auto-detected as "special" (no keyword match)
        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.election_type == "special"

    @pytest.mark.asyncio
    async def test_explicit_type_overrides_detection(self):
        """When election_type is explicitly provided, it overrides auto-detection."""
        feed = _make_multi_race_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="general",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.election_type == "general"

    @pytest.mark.asyncio
    async def test_auto_finalize_old_election(self):
        """Elections older than 14 days are created with status='finalized'."""
        feed = _make_multi_race_feed()  # date "2025-11-04" → well over 14 days ago
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            result = await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.status == "finalized"
        assert result.elections[0].status == "finalized"

    @pytest.mark.asyncio
    @time_machine.travel("2026-02-16", tick=False)
    async def test_active_for_recent_election(self):
        """Elections within 14 days are created with status='active'."""
        feed = _make_recent_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            result = await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.status == "active"
        assert result.elections[0].status == "active"

    @pytest.mark.asyncio
    async def test_skip_refresh_for_finalized(self):
        """Auto-refresh is skipped for finalized elections even when auto_refresh=True."""
        feed = _make_multi_race_feed()  # old date → finalized
        session = AsyncMock()

        mock_elections = [_mock_election("S10"), _mock_election("S11")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=True,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ),
            patch(
                "voter_api.services.election_service.refresh_single_election",
                new_callable=AsyncMock,
            ) as mock_refresh,
        ):
            result = await import_feed(session, request)

        # Refresh should NOT be called for finalized elections
        assert mock_refresh.await_count == 0
        assert result.elections[0].refreshed is False
        assert result.elections[0].status == "finalized"

    @pytest.mark.asyncio
    @time_machine.travel("2026-02-16", tick=False)
    async def test_exactly_14_days_is_active(self):
        """An election dated exactly 14 days ago is still active (strict >)."""
        feed = _make_boundary_feed(days_ago=14)
        session = AsyncMock()

        mock_elections = [_mock_election("S10")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            result = await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.status == "active"
        assert result.elections[0].status == "active"

    @pytest.mark.asyncio
    @time_machine.travel("2026-02-16", tick=False)
    async def test_15_days_is_finalized(self):
        """An election dated 15 days ago is finalized."""
        feed = _make_boundary_feed(days_ago=15)
        session = AsyncMock()

        mock_elections = [_mock_election("S10")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type="special",
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            result = await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.status == "finalized"
        assert result.elections[0].status == "finalized"

    @pytest.mark.asyncio
    async def test_auto_detect_general_from_feed_name(self):
        """Auto-detect resolves 'general' when feed name contains the keyword."""
        feed = _make_general_feed()
        session = AsyncMock()

        mock_elections = [_mock_election("S10")]

        request = FeedImportRequest(
            data_source_url="https://results.sos.ga.gov/feed.json",
            election_type=None,
            auto_refresh=False,
        )

        with (
            patch(
                "voter_api.services.election_service.fetch_election_results",
                new_callable=AsyncMock,
                return_value=feed,
            ),
            patch(
                "voter_api.services.election_service.get_settings",
                return_value=_mock_settings(),
            ),
            patch(
                "voter_api.services.election_service.create_election",
                new_callable=AsyncMock,
                side_effect=mock_elections,
            ) as mock_create,
        ):
            await import_feed(session, request)

        create_req = mock_create.call_args_list[0][0][1]
        assert create_req.election_type == "general"
