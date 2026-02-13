"""Geocoding API endpoints — single-address geocode, point lookup, verify, batch, and cache."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.models.user import User
from voter_api.schemas.geocoding import (
    AddressGeocodeResponse,
    BatchGeocodingRequest,
    CacheStatsResponse,
    GeocodingJobResponse,
)
from voter_api.services.geocoding_service import (
    create_geocoding_job,
    geocode_single_address,
    get_cache_stats,
    get_geocoding_job,
    process_geocoding_job,
)

geocoding_router = APIRouter(prefix="/geocoding", tags=["geocoding"])


@geocoding_router.get(
    "/geocode",
    response_model=AddressGeocodeResponse,
)
async def geocode_address(
    address: str = Query(  # noqa: B008
        ...,
        min_length=1,
        max_length=500,
        description="Freeform street address to geocode (1-500 characters)",
    ),
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> AddressGeocodeResponse:
    """Geocode a single freeform address to geographic coordinates."""
    stripped = address.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Address must not be empty or whitespace-only.",
        )

    try:
        result = await geocode_single_address(session, stripped)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address could not be geocoded. The provider could not match the submitted address to a location.",
        )

    return result


@geocoding_router.post(
    "/batch",
    response_model=GeocodingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_role("admin"))],
)
async def trigger_batch_geocoding(
    request: BatchGeocodingRequest,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> GeocodingJobResponse:
    """Trigger a batch geocoding job (admin only)."""
    job = await create_geocoding_job(
        session,
        provider=request.provider,
        county=request.county,
        force_regeocode=request.force_regeocode,
        triggered_by=current_user.id,
    )

    # Run geocoding in background
    async def _run_geocoding() -> None:
        from voter_api.core.database import get_session_factory

        factory = get_session_factory()
        async with factory() as bg_session:
            bg_job = await get_geocoding_job(bg_session, job.id)
            if bg_job:
                await process_geocoding_job(bg_session, bg_job)

    task_runner.submit_task(_run_geocoding())

    return GeocodingJobResponse.model_validate(job)


@geocoding_router.get(
    "/status/{job_id}",
    response_model=GeocodingJobResponse,
)
async def get_geocoding_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> GeocodingJobResponse:
    """Get the status of a geocoding job."""
    job = await get_geocoding_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Geocoding job not found")
    return GeocodingJobResponse.model_validate(job)


@geocoding_router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
)
async def get_cache_statistics(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> CacheStatsResponse:
    """Get per-provider geocoding cache statistics."""
    stats = await get_cache_stats(session)
    return CacheStatsResponse(providers=stats)
