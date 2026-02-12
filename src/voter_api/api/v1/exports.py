"""Export API endpoints for bulk data export operations."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.config import Settings, get_settings
from voter_api.core.database import get_session_factory
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.export import (
    ExportJobResponse,
    ExportRequest,
    PaginatedExportJobResponse,
)
from voter_api.services.export_service import (
    create_export_job,
    get_export_job,
    list_export_jobs,
    process_export,
)

exports_router = APIRouter(prefix="/exports", tags=["exports"])


def _build_download_url(job_id: uuid.UUID, settings: Settings) -> str:
    """Build the download URL for a completed export."""
    return f"{settings.api_v1_prefix}/exports/{job_id}/download"


def _job_to_response(job: object, settings: Settings) -> ExportJobResponse:
    """Convert an ExportJob to response with download URL."""
    response = ExportJobResponse.model_validate(job)
    if response.status == "completed":
        response.download_url = _build_download_url(response.id, settings)
    return response


@exports_router.post(
    "",
    response_model=ExportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_export(
    request: ExportRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
    settings: Settings = Depends(get_settings),
) -> ExportJobResponse:
    """Request a bulk data export (admin only)."""
    job = await create_export_job(
        session,
        output_format=request.output_format,
        filters=request.filters.model_dump(exclude_none=True),
        triggered_by=current_user.id,
    )

    # Submit background processing
    export_dir = Path(settings.export_dir)

    async def _run_export() -> None:
        factory = get_session_factory()
        async with factory() as bg_session:
            bg_job = await get_export_job(bg_session, job.id)
            if bg_job:
                await process_export(bg_session, bg_job, export_dir)

    task_runner.submit_task(_run_export())

    return _job_to_response(job, settings)


@exports_router.get(
    "",
    response_model=PaginatedExportJobResponse,
)
async def list_exports(
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PaginatedExportJobResponse:
    """List export jobs."""
    jobs, total = await list_export_jobs(
        session,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    return PaginatedExportJobResponse(
        items=[_job_to_response(j, settings) for j in jobs],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=(total + page_size - 1) // page_size,
        ),
    )


@exports_router.get(
    "/{job_id}",
    response_model=ExportJobResponse,
)
async def get_export_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ExportJobResponse:
    """Get export job status."""
    job = await get_export_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    return _job_to_response(job, settings)


@exports_router.get(
    "/{job_id}/download",
)
async def download_export(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Download a completed export file."""
    job = await get_export_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export not yet completed",
        )

    if not job.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )

    file_path = Path(job.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found on disk",
        )

    media_types = {
        "csv": "text/csv",
        "json": "application/json",
        "geojson": "application/geo+json",
    }

    return FileResponse(
        path=file_path,
        media_type=media_types.get(job.output_format, "application/octet-stream"),
        filename=file_path.name,
    )
