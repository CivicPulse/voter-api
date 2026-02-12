"""Analysis service — orchestrates location analysis runs."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.analyzer.comparator import compare_boundaries, extract_registered_boundaries
from voter_api.lib.analyzer.spatial import find_voter_boundaries
from voter_api.models.analysis_result import AnalysisResult
from voter_api.models.analysis_run import AnalysisRun
from voter_api.models.geocoded_location import GeocodedLocation
from voter_api.models.voter import Voter

ANALYSIS_BATCH_SIZE = 100


async def create_analysis_run(
    session: AsyncSession,
    *,
    triggered_by: uuid.UUID | None = None,
    notes: str | None = None,
) -> AnalysisRun:
    """Create a new analysis run record.

    Args:
        session: Database session.
        triggered_by: User ID who triggered the run.
        notes: Optional notes for this run.

    Returns:
        The created AnalysisRun.
    """
    run = AnalysisRun(
        triggered_by=triggered_by,
        status="pending",
        notes=notes,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(f"Created analysis run {run.id}")
    return run


async def process_analysis_run(
    session: AsyncSession,
    run: AnalysisRun,
    county: str | None = None,
    batch_size: int = ANALYSIS_BATCH_SIZE,
) -> AnalysisRun:
    """Process a full analysis run.

    Finds eligible voters (geocoded with primary location), performs
    spatial analysis, compares against registered boundaries, and stores results.

    Args:
        session: Database session.
        run: The AnalysisRun to process.
        county: Optional county filter.
        batch_size: Number of voters to process per batch.

    Returns:
        The updated AnalysisRun with summary counts.
    """
    run.status = "running"
    run.started_at = datetime.now(UTC)
    await session.commit()

    total_analyzed = 0
    match_count = 0
    mismatch_count = 0
    unable_count = 0

    try:
        # Resume from checkpoint if available
        offset = run.last_processed_voter_offset or 0

        while True:
            # Find eligible voters: those with a primary geocoded location
            voter_query = (
                select(Voter)
                .join(
                    GeocodedLocation,
                    (GeocodedLocation.voter_id == Voter.id) & (GeocodedLocation.is_primary.is_(True)),
                )
                .where(Voter.present_in_latest_import.is_(True))
            )

            if county:
                voter_query = voter_query.where(Voter.county == county)

            voter_query = voter_query.order_by(Voter.id).offset(offset).limit(batch_size)

            result = await session.execute(voter_query)
            voters = list(result.scalars().all())

            if not voters:
                break

            for voter in voters:
                # Get the voter's primary geocoded location
                primary_loc = next(
                    (loc for loc in voter.geocoded_locations if loc.is_primary),
                    None,
                )

                if not primary_loc:
                    unable_count += 1
                    total_analyzed += 1
                    await _store_result(
                        session,
                        run_id=run.id,
                        voter_id=voter.id,
                        determined={},
                        registered=extract_registered_boundaries(voter),
                        match_status="unable-to-analyze",
                        mismatch_details=None,
                    )
                    continue

                # Spatial analysis: find containing boundaries
                determined = await find_voter_boundaries(session, primary_loc)

                # Extract registered boundaries from voter record
                registered = extract_registered_boundaries(voter)

                # Compare and classify
                comparison = compare_boundaries(determined, registered)

                await _store_result(
                    session,
                    run_id=run.id,
                    voter_id=voter.id,
                    determined=comparison.determined_boundaries,
                    registered=comparison.registered_boundaries,
                    match_status=comparison.match_status,
                    mismatch_details=comparison.mismatch_details or None,
                )

                total_analyzed += 1
                if comparison.match_status == "match":
                    match_count += 1
                elif comparison.match_status == "unable-to-analyze":
                    unable_count += 1
                else:
                    mismatch_count += 1

            offset += len(voters)

            # Checkpoint: persist progress
            run.last_processed_voter_offset = offset
            await session.commit()

            logger.info(f"Analysis run {run.id}: processed {offset} voters so far")

        # Complete the run
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        run.total_voters_analyzed = total_analyzed
        run.match_count = match_count
        run.mismatch_count = mismatch_count
        run.unable_to_analyze_count = unable_count
        await session.commit()
        await session.refresh(run)

        logger.info(
            f"Analysis run {run.id} completed: "
            f"{total_analyzed} analyzed, {match_count} match, "
            f"{mismatch_count} mismatch, {unable_count} unable"
        )

    except Exception:
        run.status = "failed"
        run.total_voters_analyzed = total_analyzed
        run.match_count = match_count
        run.mismatch_count = mismatch_count
        run.unable_to_analyze_count = unable_count
        await session.commit()
        logger.exception(f"Analysis run {run.id} failed")
        raise

    return run


async def _store_result(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    voter_id: uuid.UUID,
    determined: dict,
    registered: dict,
    match_status: str,
    mismatch_details: list | None,
) -> AnalysisResult:
    """Store a single analysis result."""
    result = AnalysisResult(
        analysis_run_id=run_id,
        voter_id=voter_id,
        determined_boundaries=determined,
        registered_boundaries=registered,
        match_status=match_status,
        mismatch_details=mismatch_details,
    )
    session.add(result)
    return result


async def get_analysis_run(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> AnalysisRun | None:
    """Get an analysis run by ID."""
    result = await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
    return result.scalar_one_or_none()


async def list_analysis_runs(
    session: AsyncSession,
    *,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AnalysisRun], int]:
    """List analysis runs with optional status filter.

    Args:
        session: Database session.
        status_filter: Optional status to filter by.
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (runs, total count).
    """
    query = select(AnalysisRun)
    count_query = select(func.count(AnalysisRun.id))

    if status_filter:
        query = query.where(AnalysisRun.status == status_filter)
        count_query = count_query.where(AnalysisRun.status == status_filter)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(AnalysisRun.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    runs = list(result.scalars().all())

    return runs, total


async def list_analysis_results(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    match_status: str | None = None,
    county: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AnalysisResult], int]:
    """List analysis results for a run with optional filters.

    Args:
        session: Database session.
        run_id: The analysis run ID.
        match_status: Optional match status filter.
        county: Optional county filter (joins to voter).
        page: Page number.
        page_size: Items per page.

    Returns:
        Tuple of (results, total count).
    """
    query = select(AnalysisResult).where(AnalysisResult.analysis_run_id == run_id)
    count_query = select(func.count(AnalysisResult.id)).where(AnalysisResult.analysis_run_id == run_id)

    if match_status:
        query = query.where(AnalysisResult.match_status == match_status)
        count_query = count_query.where(AnalysisResult.match_status == match_status)

    if county:
        query = query.join(Voter, AnalysisResult.voter_id == Voter.id).where(Voter.county == county)
        count_query = count_query.join(Voter, AnalysisResult.voter_id == Voter.id).where(Voter.county == county)

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(AnalysisResult.analyzed_at).offset(offset).limit(page_size)
    result = await session.execute(query)
    results = list(result.scalars().all())

    return results, total


async def compare_runs(
    session: AsyncSession,
    run_id_a: uuid.UUID,
    run_id_b: uuid.UUID,
    *,
    county: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Compare results across two analysis runs.

    Args:
        session: Database session.
        run_id_a: First run ID.
        run_id_b: Second run ID.
        county: Optional county filter.
        page: Page number for items.
        page_size: Items per page.

    Returns:
        Dict with run_a, run_b, summary, and items.
    """
    run_a = await get_analysis_run(session, run_id_a)
    run_b = await get_analysis_run(session, run_id_b)

    if not run_a or not run_b:
        return {"error": "One or both runs not found"}

    # Get results from both runs
    results_a_query = select(AnalysisResult).where(AnalysisResult.analysis_run_id == run_id_a)
    results_b_query = select(AnalysisResult).where(AnalysisResult.analysis_run_id == run_id_b)

    if county:
        results_a_query = results_a_query.join(Voter, AnalysisResult.voter_id == Voter.id).where(Voter.county == county)
        results_b_query = results_b_query.join(Voter, AnalysisResult.voter_id == Voter.id).where(Voter.county == county)

    result_a = await session.execute(results_a_query)
    result_b = await session.execute(results_b_query)

    a_by_voter: dict[uuid.UUID, AnalysisResult] = {r.voter_id: r for r in result_a.scalars().all()}
    b_by_voter: dict[uuid.UUID, AnalysisResult] = {r.voter_id: r for r in result_b.scalars().all()}

    # Compare common voters
    common_voters = set(a_by_voter.keys()) & set(b_by_voter.keys())
    newly_matched = 0
    newly_mismatched = 0
    unchanged = 0
    items: list[dict] = []

    for voter_id in sorted(common_voters):
        ra = a_by_voter[voter_id]
        rb = b_by_voter[voter_id]
        changed = ra.match_status != rb.match_status

        if changed:
            if rb.match_status == "match":
                newly_matched += 1
            else:
                newly_mismatched += 1
        else:
            unchanged += 1

        items.append(
            {
                "voter_id": voter_id,
                "voter_registration_number": ra.voter.voter_registration_number if ra.voter else "",
                "status_in_run_a": ra.match_status,
                "status_in_run_b": rb.match_status,
                "changed": changed,
            }
        )

    # Apply pagination to items
    total_compared = len(items)
    offset = (page - 1) * page_size
    paged_items = items[offset : offset + page_size]

    return {
        "run_a": run_a,
        "run_b": run_b,
        "summary": {
            "newly_matched": newly_matched,
            "newly_mismatched": newly_mismatched,
            "unchanged": unchanged,
            "total_compared": total_compared,
        },
        "items": paged_items,
    }
