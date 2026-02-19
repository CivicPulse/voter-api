"""Import API endpoints.

POST /imports/voters (multipart file upload), POST /imports/voter-history,
GET /imports (list jobs), GET /imports/{job_id} (status),
GET /imports/{job_id}/diff (diff report).
"""

import math
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.config import Settings, get_settings
from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta, PaginationParams
from voter_api.schemas.imports import ImportDiffResponse, ImportJobResponse, PaginatedImportJobResponse
from voter_api.services import import_service
from voter_api.services.boundary_service import import_boundaries

router = APIRouter(prefix="/imports", tags=["imports"])

# Max file sizes for uploads
MAX_VOTER_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
MAX_BOUNDARY_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_VOTER_HISTORY_FILE_SIZE = 100 * 1024 * 1024  # 100 MB (FR-005)
_NO_FILE_DETAIL = "No file provided"


@router.post("/voters", response_model=ImportJobResponse, status_code=202)
async def import_voters(
    file: UploadFile,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportJobResponse:
    """Upload and import a voter CSV file (admin only)."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_NO_FILE_DETAIL)

    # Save uploaded file to temp location with size limit
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        if len(content) > MAX_VOTER_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size of {MAX_VOTER_FILE_SIZE // (1024 * 1024)} MB",
            )
        tmp.write(content)
        tmp_path = Path(tmp.name)

    job = await import_service.create_import_job(
        session,
        file_name=file.filename,
        file_type="voter_csv",
        triggered_by=current_user.id,
    )

    # Submit background task
    async def _run_import() -> None:
        from voter_api.core.database import get_session_factory

        try:
            factory = get_session_factory()
            async with factory() as bg_session:
                bg_job = await import_service.get_import_job(bg_session, job.id)
                if bg_job:
                    await import_service.process_voter_import(bg_session, bg_job, tmp_path, settings.import_batch_size)
        finally:
            tmp_path.unlink(missing_ok=True)

    task_runner.submit_task(_run_import())
    return ImportJobResponse.model_validate(job)


@router.post("/voter-history", response_model=ImportJobResponse, status_code=202)
async def import_voter_history(
    file: UploadFile,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ImportJobResponse:
    """Upload and import a voter history CSV file (admin only)."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_NO_FILE_DETAIL,
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        content = await file.read()
        if len(content) > MAX_VOTER_HISTORY_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size of {MAX_VOTER_HISTORY_FILE_SIZE // (1024 * 1024)} MB",
            )
        tmp.write(content)
        tmp_path = Path(tmp.name)

    job = await import_service.create_import_job(
        session,
        file_name=file.filename,
        file_type="voter_history",
        triggered_by=current_user.id,
    )

    async def _run_import() -> None:
        from voter_api.core.database import get_session_factory
        from voter_api.services.voter_history_service import process_voter_history_import

        try:
            factory = get_session_factory()
            async with factory() as bg_session:
                bg_job = await import_service.get_import_job(bg_session, job.id)
                if bg_job:
                    await process_voter_history_import(bg_session, bg_job, tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    task_runner.submit_task(_run_import())
    return ImportJobResponse.model_validate(job)


@router.post("/boundaries", status_code=202)
async def import_boundary_file(
    file: UploadFile,
    boundary_type: str,
    source: str,
    current_user: Annotated[User, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    county: str | None = None,
) -> dict:
    """Upload and import a boundary file (shapefile or GeoJSON, admin only)."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_NO_FILE_DETAIL)

    # Determine suffix from filename
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".shp", ".geojson", ".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format: {suffix}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        if len(content) > MAX_BOUNDARY_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size of {MAX_BOUNDARY_FILE_SIZE // (1024 * 1024)} MB",
            )
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        boundaries = await import_boundaries(
            session,
            file_path=tmp_path,
            boundary_type=boundary_type,
            source=source,
            county=county,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return {"imported": len(boundaries), "boundary_type": boundary_type}


@router.get("", response_model=PaginatedImportJobResponse)
async def list_imports(
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    pagination: Annotated[PaginationParams, Depends()],
    file_type: str | None = None,
    import_status: str | None = None,
) -> PaginatedImportJobResponse:
    """List import jobs with optional filters."""
    jobs, total = await import_service.list_import_jobs(
        session, file_type=file_type, status=import_status, page=pagination.page, page_size=pagination.page_size
    )
    return PaginatedImportJobResponse(
        items=[ImportJobResponse.model_validate(j) for j in jobs],
        pagination=PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=max(1, math.ceil(total / pagination.page_size)),
        ),
    )


@router.get("/{job_id}", response_model=ImportJobResponse)
async def get_import(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ImportJobResponse:
    """Get import job status by ID."""
    job = await import_service.get_import_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return ImportJobResponse.model_validate(job)


@router.get("/{job_id}/diff", response_model=ImportDiffResponse)
async def get_import_diff(
    job_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role("admin", "analyst"))],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> ImportDiffResponse:
    """Get the diff report for an import job."""
    diff = await import_service.get_import_diff(session, job_id)
    if diff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return diff
