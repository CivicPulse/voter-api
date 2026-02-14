"""Tests for the analysis service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.analysis_service import (
    _store_result,
    compare_runs,
    create_analysis_run,
    get_analysis_run,
    list_analysis_results,
    list_analysis_runs,
    process_analysis_run,
)


def _mock_analysis_run(**overrides: object) -> MagicMock:
    """Create a mock AnalysisRun."""
    run = MagicMock()
    run.id = uuid.uuid4()
    run.status = "pending"
    run.triggered_by = None
    run.notes = None
    run.total_voters_analyzed = None
    run.match_count = None
    run.mismatch_count = None
    run.unable_to_analyze_count = None
    run.last_processed_voter_offset = None
    run.started_at = None
    run.completed_at = None
    run.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    for key, value in overrides.items():
        setattr(run, key, value)
    return run


def _mock_voter(**overrides: object) -> MagicMock:
    """Create a mock Voter with geocoded locations."""
    voter = MagicMock()
    voter.id = uuid.uuid4()
    voter.county = "FULTON"
    voter.congressional_district = "05"
    voter.state_senate_district = "34"
    voter.state_house_district = "55"
    voter.county_precinct = "SS01"
    voter.geocoded_locations = []
    for key, value in overrides.items():
        setattr(voter, key, value)
    return voter


def _mock_location(*, is_primary: bool = True) -> MagicMock:
    """Create a mock GeocodedLocation."""
    loc = MagicMock()
    loc.is_primary = is_primary
    loc.latitude = 33.749
    loc.longitude = -84.388
    loc.voter_id = uuid.uuid4()
    loc.point = MagicMock()
    return loc


class TestCreateAnalysisRun:
    """Tests for create_analysis_run."""

    @pytest.mark.asyncio
    async def test_creates_run_with_pending_status(self) -> None:
        session = AsyncMock()
        user_id = uuid.uuid4()

        await create_analysis_run(session, triggered_by=user_id, notes="Test run")

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert added.status == "pending"
        assert added.triggered_by == user_id
        assert added.notes == "Test run"

    @pytest.mark.asyncio
    async def test_creates_run_without_optional_fields(self) -> None:
        session = AsyncMock()

        await create_analysis_run(session)

        added = session.add.call_args[0][0]
        assert added.status == "pending"
        assert added.triggered_by is None
        assert added.notes is None


class TestGetAnalysisRun:
    """Tests for get_analysis_run."""

    @pytest.mark.asyncio
    async def test_returns_run_when_found(self) -> None:
        run = _mock_analysis_run()
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = run
        session.execute.return_value = result

        found = await get_analysis_run(session, run.id)
        assert found is run

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        found = await get_analysis_run(session, uuid.uuid4())
        assert found is None


class TestListAnalysisRuns:
    """Tests for list_analysis_runs."""

    @pytest.mark.asyncio
    async def test_returns_runs_and_count(self) -> None:
        session = AsyncMock()
        runs = [_mock_analysis_run(), _mock_analysis_run()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = runs
        session.execute.side_effect = [count_result, select_result]

        result_runs, total = await list_analysis_runs(session)
        assert total == 2
        assert len(result_runs) == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [_mock_analysis_run(status="completed")]
        session.execute.side_effect = [count_result, select_result]

        runs, total = await list_analysis_runs(session, status_filter="completed")
        assert total == 1

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        runs, total = await list_analysis_runs(session, page=3, page_size=10)
        assert total == 50
        assert runs == []


class TestListAnalysisResults:
    """Tests for list_analysis_results."""

    @pytest.mark.asyncio
    async def test_returns_results_and_count(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 5
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = [MagicMock()] * 5
        session.execute.side_effect = [count_result, select_result]

        results, total = await list_analysis_results(session, run_id)
        assert total == 5
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_filter_by_match_status(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        results, total = await list_analysis_results(session, run_id, match_status="mismatch")
        assert total == 0

    @pytest.mark.asyncio
    async def test_filter_by_county(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        results, total = await list_analysis_results(session, run_id, county="FULTON")
        assert total == 0


class TestStoreResult:
    """Tests for _store_result."""

    @pytest.mark.asyncio
    async def test_creates_analysis_result(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()
        voter_id = uuid.uuid4()

        await _store_result(
            session,
            run_id=run_id,
            voter_id=voter_id,
            determined={"congressional": "05"},
            registered={"congressional": "05"},
            match_status="match",
            mismatch_details=None,
        )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.analysis_run_id == run_id
        assert added.voter_id == voter_id
        assert added.match_status == "match"
        assert added.determined_boundaries == {"congressional": "05"}


class TestProcessAnalysisRun:
    """Tests for process_analysis_run."""

    @pytest.mark.asyncio
    async def test_completes_with_no_voters(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        # First execute returns empty voter list
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.return_value = select_result

        await process_analysis_run(session, run)

        assert run.status == "completed"
        assert run.total_voters_analyzed == 0
        assert run.match_count == 0
        assert run.mismatch_count == 0

    @pytest.mark.asyncio
    async def test_processes_voter_with_match(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        loc = _mock_location(is_primary=True)
        voter = _mock_voter(geocoded_locations=[loc])

        # First call returns voters, second call returns empty (end of batch)
        result_with_voters = MagicMock()
        result_with_voters.scalars.return_value.all.return_value = [voter]
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        session.execute.side_effect = [result_with_voters, result_empty]

        comparison_result = MagicMock()
        comparison_result.determined_boundaries = {"congressional": "05"}
        comparison_result.registered_boundaries = {"congressional": "05"}
        comparison_result.match_status = "match"
        comparison_result.mismatch_details = None

        with (
            patch("voter_api.services.analysis_service.find_voter_boundaries", return_value={"congressional": "05"}),
            patch(
                "voter_api.services.analysis_service.extract_registered_boundaries",
                return_value={"congressional": "05"},
            ),
            patch("voter_api.services.analysis_service.compare_boundaries", return_value=comparison_result),
        ):
            await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.match_count == 1
        assert run.total_voters_analyzed == 1

    @pytest.mark.asyncio
    async def test_handles_voter_without_primary_location(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        voter = _mock_voter(geocoded_locations=[])

        result_with_voters = MagicMock()
        result_with_voters.scalars.return_value.all.return_value = [voter]
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        session.execute.side_effect = [result_with_voters, result_empty]

        with patch("voter_api.services.analysis_service.extract_registered_boundaries", return_value={}):
            await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.unable_to_analyze_count == 1

    @pytest.mark.asyncio
    async def test_handles_mismatch(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        loc = _mock_location(is_primary=True)
        voter = _mock_voter(geocoded_locations=[loc])

        result_with_voters = MagicMock()
        result_with_voters.scalars.return_value.all.return_value = [voter]
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        session.execute.side_effect = [result_with_voters, result_empty]

        comparison_result = MagicMock()
        comparison_result.determined_boundaries = {"congressional": "06"}
        comparison_result.registered_boundaries = {"congressional": "05"}
        comparison_result.match_status = "mismatch"
        comparison_result.mismatch_details = [{"type": "congressional", "registered": "05", "determined": "06"}]

        with (
            patch("voter_api.services.analysis_service.find_voter_boundaries", return_value={"congressional": "06"}),
            patch(
                "voter_api.services.analysis_service.extract_registered_boundaries",
                return_value={"congressional": "05"},
            ),
            patch("voter_api.services.analysis_service.compare_boundaries", return_value=comparison_result),
        ):
            await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.mismatch_count == 1

    @pytest.mark.asyncio
    async def test_failure_sets_status_to_failed(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        session.execute.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError, match="DB error"):
            await process_analysis_run(session, run)

        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_county_filter_applied(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        session.execute.return_value = result_empty

        await process_analysis_run(session, run, county="FULTON")
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_resumes_from_checkpoint(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run(last_processed_voter_offset=5)

        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        session.execute.return_value = result_empty

        await process_analysis_run(session, run)
        assert run.status == "completed"


class TestCompareRuns:
    """Tests for compare_runs."""

    @pytest.mark.asyncio
    async def test_run_not_found_returns_error(self) -> None:
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        comparison = await compare_runs(session, uuid.uuid4(), uuid.uuid4())
        assert "error" in comparison

    @pytest.mark.asyncio
    async def test_compares_matching_results(self) -> None:
        session = AsyncMock()
        run_a = _mock_analysis_run()
        run_b = _mock_analysis_run()
        voter_id = uuid.uuid4()

        result_a = MagicMock()
        result_a.voter_id = voter_id
        result_a.match_status = "match"
        result_a.voter = MagicMock()
        result_a.voter.voter_registration_number = "12345"

        result_b = MagicMock()
        result_b.voter_id = voter_id
        result_b.match_status = "match"

        # Mock session.execute calls:
        # 1. get_analysis_run(run_a) - scalar_one_or_none
        # 2. get_analysis_run(run_b) - scalar_one_or_none
        # 3. results_a select - scalars().all()
        # 4. results_b select - scalars().all()
        mock_run_a_result = MagicMock()
        mock_run_a_result.scalar_one_or_none.return_value = run_a
        mock_run_b_result = MagicMock()
        mock_run_b_result.scalar_one_or_none.return_value = run_b
        mock_results_a = MagicMock()
        mock_results_a.scalars.return_value.all.return_value = [result_a]
        mock_results_b = MagicMock()
        mock_results_b.scalars.return_value.all.return_value = [result_b]
        session.execute.side_effect = [mock_run_a_result, mock_run_b_result, mock_results_a, mock_results_b]

        comparison = await compare_runs(session, run_a.id, run_b.id)
        assert comparison["summary"]["unchanged"] == 1
        assert comparison["summary"]["total_compared"] == 1

    @pytest.mark.asyncio
    async def test_detects_newly_matched(self) -> None:
        session = AsyncMock()
        run_a = _mock_analysis_run()
        run_b = _mock_analysis_run()
        voter_id = uuid.uuid4()

        result_a = MagicMock()
        result_a.voter_id = voter_id
        result_a.match_status = "mismatch"
        result_a.voter = MagicMock()
        result_a.voter.voter_registration_number = "12345"

        result_b = MagicMock()
        result_b.voter_id = voter_id
        result_b.match_status = "match"

        mock_run_a_result = MagicMock()
        mock_run_a_result.scalar_one_or_none.return_value = run_a
        mock_run_b_result = MagicMock()
        mock_run_b_result.scalar_one_or_none.return_value = run_b
        mock_results_a = MagicMock()
        mock_results_a.scalars.return_value.all.return_value = [result_a]
        mock_results_b = MagicMock()
        mock_results_b.scalars.return_value.all.return_value = [result_b]
        session.execute.side_effect = [mock_run_a_result, mock_run_b_result, mock_results_a, mock_results_b]

        comparison = await compare_runs(session, run_a.id, run_b.id)
        assert comparison["summary"]["newly_matched"] == 1

    @pytest.mark.asyncio
    async def test_detects_newly_mismatched(self) -> None:
        session = AsyncMock()
        run_a = _mock_analysis_run()
        run_b = _mock_analysis_run()
        voter_id = uuid.uuid4()

        result_a = MagicMock()
        result_a.voter_id = voter_id
        result_a.match_status = "match"
        result_a.voter = MagicMock()
        result_a.voter.voter_registration_number = "12345"

        result_b = MagicMock()
        result_b.voter_id = voter_id
        result_b.match_status = "mismatch"

        mock_run_a_result = MagicMock()
        mock_run_a_result.scalar_one_or_none.return_value = run_a
        mock_run_b_result = MagicMock()
        mock_run_b_result.scalar_one_or_none.return_value = run_b
        mock_results_a = MagicMock()
        mock_results_a.scalars.return_value.all.return_value = [result_a]
        mock_results_b = MagicMock()
        mock_results_b.scalars.return_value.all.return_value = [result_b]
        session.execute.side_effect = [mock_run_a_result, mock_run_b_result, mock_results_a, mock_results_b]

        comparison = await compare_runs(session, run_a.id, run_b.id)
        assert comparison["summary"]["newly_mismatched"] == 1

    @pytest.mark.asyncio
    async def test_pagination_of_items(self) -> None:
        session = AsyncMock()
        run_a = _mock_analysis_run()
        run_b = _mock_analysis_run()

        # Create 3 voters with matching IDs
        voter_ids = [uuid.uuid4() for _ in range(3)]
        results_a = []
        results_b = []
        for vid in voter_ids:
            ra = MagicMock()
            ra.voter_id = vid
            ra.match_status = "match"
            ra.voter = MagicMock()
            ra.voter.voter_registration_number = str(vid)[:8]
            results_a.append(ra)

            rb = MagicMock()
            rb.voter_id = vid
            rb.match_status = "match"
            results_b.append(rb)

        mock_run_a_result = MagicMock()
        mock_run_a_result.scalar_one_or_none.return_value = run_a
        mock_run_b_result = MagicMock()
        mock_run_b_result.scalar_one_or_none.return_value = run_b
        mock_results_a = MagicMock()
        mock_results_a.scalars.return_value.all.return_value = results_a
        mock_results_b = MagicMock()
        mock_results_b.scalars.return_value.all.return_value = results_b
        session.execute.side_effect = [mock_run_a_result, mock_run_b_result, mock_results_a, mock_results_b]

        comparison = await compare_runs(session, run_a.id, run_b.id, page=1, page_size=2)
        assert len(comparison["items"]) == 2
        assert comparison["summary"]["total_compared"] == 3
