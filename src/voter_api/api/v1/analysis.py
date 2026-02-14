"""Analysis API endpoints for triggering and querying location analysis."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.database import get_session_factory
from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.analysis import (
    AnalysisComparisonResponse,
    AnalysisResultResponse,
    AnalysisRunResponse,
    ComparisonItem,
    ComparisonSummary,
    PaginatedAnalysisResultResponse,
    PaginatedAnalysisRunResponse,
    TriggerAnalysisRequest,
)
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.voter import VoterSummaryResponse
from voter_api.services.analysis_service import (
    compare_runs,
    create_analysis_run,
    get_analysis_run,
    list_analysis_results,
    list_analysis_runs,
    process_analysis_run,
)

analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])


@analysis_router.post(
    "/runs",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_analysis_run(
    request: TriggerAnalysisRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "analyst")),
) -> AnalysisRunResponse:
    """Trigger a new analysis run (admin/analyst only)."""
    run = await create_analysis_run(
        session,
        triggered_by=current_user.id,
        notes=request.notes,
    )

    # Submit background processing
    async def _run_analysis() -> None:
        factory = get_session_factory()
        async with factory() as bg_session:
            from voter_api.services.analysis_service import get_analysis_run as get_run

            bg_run = await get_run(bg_session, run.id)
            if bg_run:
                await process_analysis_run(bg_session, bg_run, county=request.county)

    task_runner.submit_task(_run_analysis())

    return AnalysisRunResponse.model_validate(run)


@analysis_router.get(
    "/runs",
    response_model=PaginatedAnalysisRunResponse,
)
async def list_runs(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(require_role("admin", "analyst")),
) -> PaginatedAnalysisRunResponse:
    """List analysis runs (admin/analyst only)."""
    runs, total = await list_analysis_runs(
        session,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    return PaginatedAnalysisRunResponse(
        items=[AnalysisRunResponse.model_validate(r) for r in runs],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@analysis_router.get(
    "/runs/{run_id}",
    response_model=AnalysisRunResponse,
)
async def get_run_detail(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(require_role("admin", "analyst")),
) -> AnalysisRunResponse:
    """Get analysis run details (admin/analyst only)."""
    run = await get_analysis_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return AnalysisRunResponse.model_validate(run)


@analysis_router.get(
    "/runs/{run_id}/results",
    response_model=PaginatedAnalysisResultResponse,
)
async def get_run_results(
    run_id: uuid.UUID,
    match_status: str | None = Query(None),
    county: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(require_role("admin", "analyst")),
) -> PaginatedAnalysisResultResponse:
    """Get analysis results for a run (admin/analyst only)."""
    run = await get_analysis_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")

    results, total = await list_analysis_results(
        session,
        run_id,
        match_status=match_status,
        county=county,
        page=page,
        page_size=page_size,
    )

    items = []
    for r in results:
        voter_summary = None
        if r.voter:
            voter_summary = VoterSummaryResponse.model_validate(r.voter)
        items.append(
            AnalysisResultResponse(
                id=r.id,
                analysis_run_id=r.analysis_run_id,
                voter_id=r.voter_id,
                voter_summary=voter_summary,
                determined_boundaries=r.determined_boundaries,
                registered_boundaries=r.registered_boundaries,
                match_status=r.match_status,
                mismatch_details=r.mismatch_details,
                analyzed_at=r.analyzed_at,
            )
        )

    return PaginatedAnalysisResultResponse(
        items=items,
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@analysis_router.get(
    "/compare",
    response_model=AnalysisComparisonResponse,
)
async def compare_analysis_runs(
    run_id_a: uuid.UUID = Query(...),
    run_id_b: uuid.UUID = Query(...),
    county: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(require_role("admin", "analyst")),
) -> AnalysisComparisonResponse:
    """Compare results across two analysis runs (admin/analyst only)."""
    comparison = await compare_runs(
        session,
        run_id_a,
        run_id_b,
        county=county,
        page=page,
        page_size=page_size,
    )

    if "error" in comparison:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=comparison["error"],
        )

    return AnalysisComparisonResponse(
        run_a=AnalysisRunResponse.model_validate(comparison["run_a"]),
        run_b=AnalysisRunResponse.model_validate(comparison["run_b"]),
        summary=ComparisonSummary(**comparison["summary"]),
        items=[ComparisonItem(**item) for item in comparison["items"]],
    )
