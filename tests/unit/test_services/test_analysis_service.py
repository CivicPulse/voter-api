"""Tests for the analysis service module."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voter_api.services.analysis_service import (
    _flush_results,
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
    """Create a mock Voter with official location."""
    voter = MagicMock()
    voter.id = uuid.uuid4()
    voter.county = "FULTON"
    voter.congressional_district = "05"
    voter.state_senate_district = "34"
    voter.state_house_district = "55"
    voter.county_precinct = "SS01"
    voter.official_point = MagicMock()  # Non-None means voter has a location
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

        _, total = await list_analysis_runs(session, status_filter="completed")
        assert total == 1

    @pytest.mark.asyncio
    async def test_pagination(self) -> None:
        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        session.execute.side_effect = [count_result, select_result]

        _, total = await list_analysis_runs(session, page=3, page_size=10)
        assert total == 50


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

        _, total = await list_analysis_results(session, run_id, match_status="mismatch")
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

        _, total = await list_analysis_results(session, run_id, county="FULTON")
        assert total == 0


class TestFlushResults:
    """Tests for _flush_results."""

    @pytest.mark.asyncio
    async def test_inserts_results_via_core(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()
        voter_id = uuid.uuid4()

        # Mock the RETURNING result
        returning_result = MagicMock()
        returning_result.all.return_value = [MagicMock()]  # 1 row inserted
        session.execute.return_value = returning_result

        results = [
            {
                "id": uuid.uuid4(),
                "analysis_run_id": run_id,
                "voter_id": voter_id,
                "determined_boundaries": {"congressional": "05"},
                "registered_boundaries": {"congressional": "05"},
                "match_status": "match",
                "mismatch_details": None,
            }
        ]

        inserted = await _flush_results(session, results)

        assert inserted == 1
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_list(self) -> None:
        session = AsyncMock()

        inserted = await _flush_results(session, [])

        assert inserted == 0
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_sub_batches_large_lists(self) -> None:
        session = AsyncMock()
        run_id = uuid.uuid4()

        # Create 600 results (exceeds _FLUSH_SUB_BATCH of 500)
        results = [
            {
                "id": uuid.uuid4(),
                "analysis_run_id": run_id,
                "voter_id": uuid.uuid4(),
                "determined_boundaries": {},
                "registered_boundaries": {},
                "match_status": "match",
                "mismatch_details": None,
            }
            for _ in range(600)
        ]

        returning_result = MagicMock()
        returning_result.all.return_value = [MagicMock()] * 500
        returning_result_2 = MagicMock()
        returning_result_2.all.return_value = [MagicMock()] * 100
        session.execute.side_effect = [returning_result, returning_result_2]

        inserted = await _flush_results(session, results)

        assert inserted == 600
        assert session.execute.call_count == 2


def _mock_process_session_with_voter(voter: MagicMock) -> AsyncMock:
    """Create a mock session for process_analysis_run with one voter batch."""
    session = AsyncMock()
    cursor_result = MagicMock()
    cursor_result.scalar_one_or_none.return_value = None
    result_with_voters = MagicMock()
    result_with_voters.scalars.return_value.all.return_value = [voter]
    flush_result = MagicMock()
    flush_result.all.return_value = [MagicMock()]
    result_empty = MagicMock()
    result_empty.scalars.return_value.all.return_value = []
    bulk_update_result = MagicMock()
    session.execute.side_effect = [
        cursor_result,
        result_with_voters,
        flush_result,
        result_empty,
        bulk_update_result,
    ]
    return session


def _mock_compare_session(
    run_a: MagicMock,
    run_b: MagicMock,
    result_a: MagicMock,
    result_b: MagicMock,
) -> AsyncMock:
    """Create a mock session for compare_runs."""
    session = AsyncMock()
    mock_run_a_result = MagicMock()
    mock_run_a_result.scalar_one_or_none.return_value = run_a
    mock_run_b_result = MagicMock()
    mock_run_b_result.scalar_one_or_none.return_value = run_b
    mock_results_a = MagicMock()
    mock_results_a.scalars.return_value.all.return_value = [result_a]
    mock_results_b = MagicMock()
    mock_results_b.scalars.return_value.all.return_value = [result_b]
    session.execute.side_effect = [
        mock_run_a_result,
        mock_run_b_result,
        mock_results_a,
        mock_results_b,
    ]
    return session


class TestProcessAnalysisRun:
    """Tests for process_analysis_run."""

    @pytest.mark.asyncio
    async def test_completes_with_no_voters(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        # 1st: resume cursor query (MAX voter_id) returns None (fresh run)
        cursor_result = MagicMock()
        cursor_result.scalar_one_or_none.return_value = None
        # 2nd: voter query returns empty
        select_result = MagicMock()
        select_result.scalars.return_value.all.return_value = []
        # 3rd: bulk-update of has_district_mismatch
        bulk_update_result = MagicMock()
        session.execute.side_effect = [cursor_result, select_result, bulk_update_result]

        await process_analysis_run(session, run)

        assert run.status == "completed"
        assert run.total_voters_analyzed == 0
        assert run.match_count == 0
        assert run.mismatch_count == 0

    @pytest.mark.asyncio
    async def test_processes_voter_with_match(self) -> None:
        run = _mock_analysis_run()
        voter = _mock_voter()
        session = _mock_process_session_with_voter(voter)

        comparison_result = MagicMock()
        comparison_result.determined_boundaries = {"congressional": "05"}
        comparison_result.registered_boundaries = {"congressional": "05"}
        comparison_result.match_status = "match"
        comparison_result.mismatch_details = None

        with (
            patch(
                "voter_api.services.analysis_service.find_boundaries_for_point",
                new_callable=AsyncMock,
                return_value={"congressional": "05"},
            ),
            patch(
                "voter_api.services.analysis_service.extract_registered_boundaries",
                return_value={"congressional": "05"},
            ),
            patch(
                "voter_api.services.analysis_service.compare_boundaries",
                return_value=comparison_result,
            ),
        ):
            await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.match_count == 1
        assert run.total_voters_analyzed == 1

    @pytest.mark.asyncio
    async def test_skips_voter_without_official_point(self) -> None:
        """Voters without official_point are excluded by the query filter, so 0 analyzed."""
        session = AsyncMock()
        run = _mock_analysis_run()

        # 1st: resume cursor (fresh run)
        cursor_result = MagicMock()
        cursor_result.scalar_one_or_none.return_value = None
        # 2nd: voter query returns empty
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        # 3rd: bulk-update of has_district_mismatch
        bulk_update_result = MagicMock()
        session.execute.side_effect = [cursor_result, result_empty, bulk_update_result]

        await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.total_voters_analyzed == 0

    @pytest.mark.asyncio
    async def test_handles_mismatch(self) -> None:
        run = _mock_analysis_run()
        voter = _mock_voter()
        session = _mock_process_session_with_voter(voter)

        comparison_result = MagicMock()
        comparison_result.determined_boundaries = {"congressional": "06"}
        comparison_result.registered_boundaries = {"congressional": "05"}
        comparison_result.match_status = "mismatch"
        comparison_result.mismatch_details = [{"type": "congressional", "registered": "05", "determined": "06"}]

        with (
            patch(
                "voter_api.services.analysis_service.find_boundaries_for_point",
                new_callable=AsyncMock,
                return_value={"congressional": "06"},
            ),
            patch(
                "voter_api.services.analysis_service.extract_registered_boundaries",
                return_value={"congressional": "05"},
            ),
            patch(
                "voter_api.services.analysis_service.compare_boundaries",
                return_value=comparison_result,
            ),
        ):
            await process_analysis_run(session, run, batch_size=10)

        assert run.status == "completed"
        assert run.mismatch_count == 1

    @pytest.mark.asyncio
    async def test_failure_sets_status_to_failed(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        # Resume cursor query fails
        session.execute.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError, match="DB error"):
            await process_analysis_run(session, run)

        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_county_filter_applied(self) -> None:
        session = AsyncMock()
        run = _mock_analysis_run()

        # 1st: resume cursor (fresh run)
        cursor_result = MagicMock()
        cursor_result.scalar_one_or_none.return_value = None
        # 2nd: voter query returns empty
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        # 3rd: bulk-update of has_district_mismatch
        bulk_update_result = MagicMock()
        session.execute.side_effect = [cursor_result, result_empty, bulk_update_result]

        await process_analysis_run(session, run, county="FULTON")
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_resumes_from_checkpoint(self) -> None:
        session = AsyncMock()
        last_vid = uuid.uuid4()
        run = _mock_analysis_run(last_processed_voter_offset=5)

        # 1st: resume cursor returns a voter_id (resuming)
        cursor_result = MagicMock()
        cursor_result.scalar_one_or_none.return_value = last_vid
        # 2nd: counter restore query
        counter_result = MagicMock()
        counter_result.one.return_value = (5, 3, 1, 1)  # total, match, mismatch, unable
        # 3rd: voter query returns empty (nothing left)
        result_empty = MagicMock()
        result_empty.scalars.return_value.all.return_value = []
        # 4th: bulk-update of has_district_mismatch
        bulk_update_result = MagicMock()
        session.execute.side_effect = [
            cursor_result,
            counter_result,
            result_empty,
            bulk_update_result,
        ]

        await process_analysis_run(session, run)
        assert run.status == "completed"
        assert run.total_voters_analyzed == 5
        assert run.match_count == 3
        assert run.mismatch_count == 1
        assert run.unable_to_analyze_count == 1


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

        session = _mock_compare_session(run_a, run_b, result_a, result_b)

        comparison = await compare_runs(session, run_a.id, run_b.id)
        assert comparison["summary"]["unchanged"] == 1
        assert comparison["summary"]["total_compared"] == 1

    @pytest.mark.asyncio
    async def test_detects_newly_matched(self) -> None:
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

        session = _mock_compare_session(run_a, run_b, result_a, result_b)

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
