"""Geocoding API endpoints — single-address geocode, point lookup, verify, batch, and cache."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.config import get_settings
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.lib.geocoder import get_all_provider_metadata, get_configured_providers
from voter_api.lib.geocoder.base import GeocodingProviderError
from voter_api.lib.geocoder.point_lookup import validate_georgia_coordinates
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta, PaginationParams
from voter_api.schemas.geocoding import (
    AddressGeocodeResponse,
    AddressVerifyResponse,
    BatchGeocodingRequest,
    CacheStatsResponse,
    CancelJobResponse,
    DistrictInfo,
    GeocodedLocationResponse,
    GeocodingJobResponse,
    MarkFailedRequest,
    PaginatedGeocodingJobResponse,
    PointLookupResponse,
    ProviderGeocodeResult,
    ProviderInfo,
    ProvidersListResponse,
    VoterGeocodeAllResponse,
)
from voter_api.services.boundary_service import find_boundaries_at_point
from voter_api.services.geocoding_service import (
    GeocodingJobNotFoundError,
    GeocodingJobTerminalStateError,
    cancel_geocoding_job,
    create_geocoding_job,
    geocode_single_address,
    geocode_voter_all_providers,
    get_cache_stats,
    get_geocoding_job,
    list_geocoding_jobs,
    mark_geocoding_job_failed,
    process_geocoding_job,
    verify_address,
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
) -> AddressGeocodeResponse:
    """Geocode a single freeform address to geographic coordinates.

    Public endpoint — no authentication required.

    Args:
        address: Freeform street address to geocode (1-500 characters).
        session: Async database session (injected).

    Returns:
        Geocoded response with coordinates, confidence, and provider metadata.

    Raises:
        HTTPException: 422 if address is empty/whitespace, 404 if not geocodable,
            502 if the geocoding provider is unavailable.
    """
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
    except GeocodingProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Geocoding provider is temporarily unavailable. Please retry later.",
        ) from e

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address could not be geocoded. The provider could not match the submitted address to a location.",
        )

    return result


@geocoding_router.get(
    "/verify",
    response_model=AddressVerifyResponse,
)
async def verify_address_endpoint(
    address: str = Query(  # noqa: B008
        ...,
        min_length=1,
        max_length=500,
        description="Freeform street address to verify (1-500 characters)",
    ),
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AddressVerifyResponse:
    """Verify and autocomplete a freeform address.

    Public endpoint — no authentication required.

    Args:
        address: Freeform street address to verify (1-500 characters).
        session: Async database session (injected).

    Returns:
        Verification result with normalized address, component validation,
        and autocomplete suggestions.

    Raises:
        HTTPException: 422 if address is empty/whitespace, 502 if the
            verification provider is unavailable, 500 on unexpected errors.
    """
    stripped = address.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Address must not be empty or whitespace-only.",
        )

    try:
        return await verify_address(session, stripped)
    except GeocodingProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Address verification provider is temporarily unavailable.",
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error during address verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during address verification.",
        ) from e


@geocoding_router.get(
    "/point-lookup",
    response_model=PointLookupResponse,
)
async def point_lookup_districts(
    lat: float = Query(..., description="WGS84 latitude"),  # noqa: B008
    lng: float = Query(..., description="WGS84 longitude"),  # noqa: B008
    accuracy: float | None = Query(  # noqa: B008
        None, le=100, description="GPS accuracy radius in meters (max 100)"
    ),
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> PointLookupResponse:
    """Look up boundary districts for a geographic point.

    Public endpoint — no authentication required.

    Args:
        lat: WGS84 latitude of the point to look up.
        lng: WGS84 longitude of the point to look up.
        accuracy: Optional GPS accuracy radius in meters (max 100).
        session: Async database session (injected).

    Returns:
        Point lookup response with matching district boundaries.

    Raises:
        HTTPException: 422 if coordinates are outside Georgia or accuracy
            exceeds 100m, 500 on unexpected errors.
    """
    try:
        validate_georgia_coordinates(lat, lng)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    try:
        boundaries = await find_boundaries_at_point(session, lat, lng, accuracy)
    except Exception as e:
        logger.error(f"Unexpected error during point lookup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during point lookup.",
        ) from e

    districts = [
        DistrictInfo(
            boundary_type=b.boundary_type,
            name=b.name,
            boundary_identifier=b.boundary_identifier,
            boundary_id=b.id,
            metadata=b.properties or {},
        )
        for b in boundaries
    ]

    return PointLookupResponse(
        latitude=lat,
        longitude=lng,
        accuracy=accuracy,
        districts=districts,
    )


@geocoding_router.post(
    "/voter/{voter_id}/geocode-all",
    response_model=VoterGeocodeAllResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def geocode_voter_all(
    voter_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> VoterGeocodeAllResponse:
    """Geocode a voter's address with all available providers (admin only).

    Reconstructs the voter's residence address and runs it through every
    registered geocoding provider, storing a GeocodedLocation for each
    successful result.
    """
    try:
        result = await geocode_voter_all_providers(session, voter_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    return VoterGeocodeAllResponse(
        voter_id=result["voter_id"],
        address=result["address"],
        providers=[ProviderGeocodeResult(**p) for p in result["providers"]],
        locations=[GeocodedLocationResponse.model_validate(loc) for loc in result["locations"]],
    )


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

    # Resolve fallback providers if requested
    use_fallback = request.fallback
    fallback_providers = None
    if use_fallback:
        settings = get_settings()
        fallback_providers = get_configured_providers(settings)

    # Run geocoding in background
    async def _run_geocoding() -> None:
        from voter_api.core.database import get_session_factory

        factory = get_session_factory()
        async with factory() as bg_session:
            bg_job = await get_geocoding_job(bg_session, job.id)
            if bg_job:
                await process_geocoding_job(
                    bg_session,
                    bg_job,
                    fallback=use_fallback,
                    fallback_providers=fallback_providers,
                )
            else:
                logger.error(f"Background geocoding job {job.id} not found")

    task_runner.submit_task(_run_geocoding())

    return GeocodingJobResponse.model_validate(job)


@geocoding_router.get(
    "/batch",
    response_model=PaginatedGeocodingJobResponse,
    dependencies=[Depends(require_role("admin", "analyst"))],
)
async def list_batch_jobs(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    pagination: PaginationParams = Depends(),  # noqa: B008
    job_status: str | None = Query(None, alias="status"),
    provider: str | None = None,
    county: str | None = None,
) -> PaginatedGeocodingJobResponse:
    """List batch geocoding jobs.

    Args:
        session: Async database session (injected).
        pagination: Pagination parameters.
        job_status: Optional job status filter (query param alias: ``status``).
        provider: Optional provider filter.
        county: Optional county filter.

    Returns:
        Paginated geocoding jobs response with items and pagination metadata.
    """
    jobs, total = await list_geocoding_jobs(
        session,
        status=job_status,
        provider=provider,
        county=county,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedGeocodingJobResponse(
        items=[GeocodingJobResponse.model_validate(j) for j in jobs],
        pagination=PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=(total + pagination.page_size - 1) // pagination.page_size,
        ),
    )


@geocoding_router.get(
    "/jobs",
    response_model=PaginatedGeocodingJobResponse,
    dependencies=[Depends(require_role("admin", "analyst"))],
)
async def list_jobs(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
    pagination: PaginationParams = Depends(),  # noqa: B008
    job_status: str | None = None,
    provider: str | None = None,
    county: str | None = None,
) -> PaginatedGeocodingJobResponse:
    """List geocoding jobs with optional filters (admin/analyst only)."""
    jobs, total = await list_geocoding_jobs(
        session,
        status=job_status,
        provider=provider,
        county=county,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedGeocodingJobResponse(
        items=[GeocodingJobResponse.model_validate(j) for j in jobs],
        pagination=PaginationMeta(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=(total + pagination.page_size - 1) // pagination.page_size,
        ),
    )


@geocoding_router.patch(
    "/jobs/{job_id}/cancel",
    response_model=CancelJobResponse,
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Geocoding job not found"},
        409: {"description": "Job already in terminal state"},
    },
    dependencies=[Depends(require_role("admin"))],
)
async def cancel_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> CancelJobResponse:
    """Cancel a running or pending geocoding job (admin only).

    Args:
        job_id: Geocoding job UUID.
        session: Async database session (injected).

    Returns:
        CancelJobResponse with the updated job status.

    Raises:
        HTTPException: 404 if job does not exist; 409 if job is already terminal.
    """
    try:
        job = await cancel_geocoding_job(session, job_id)
    except GeocodingJobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geocoding job not found",
        ) from e
    except GeocodingJobTerminalStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already in terminal state '{e.current_status}' and cannot be cancelled",
        ) from e

    return CancelJobResponse(
        id=job.id,
        status=job.status,
        completed_at=job.completed_at,
        message="Job cancelled successfully",
    )


@geocoding_router.patch(
    "/jobs/{job_id}/fail",
    response_model=CancelJobResponse,
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        404: {"description": "Geocoding job not found"},
        409: {"description": "Job already in terminal state"},
    },
    dependencies=[Depends(require_role("admin"))],
)
async def mark_job_failed(
    job_id: uuid.UUID,
    body: MarkFailedRequest | None = None,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> CancelJobResponse:
    """Mark a running or pending geocoding job as failed (admin only).

    Args:
        job_id: Geocoding job UUID.
        body: Optional request body with a failure reason.
        session: Async database session (injected).

    Returns:
        CancelJobResponse with the updated job status.

    Raises:
        HTTPException: 404 if job does not exist; 409 if job is already terminal.
    """
    reason = body.reason if body else None
    try:
        job = await mark_geocoding_job_failed(session, job_id, reason=reason)
    except GeocodingJobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geocoding job not found",
        ) from e
    except GeocodingJobTerminalStateError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already in terminal state '{e.current_status}' and cannot be marked as failed",
        ) from e

    return CancelJobResponse(
        id=job.id,
        status=job.status,
        completed_at=job.completed_at,
        message="Job marked as failed",
    )


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


@geocoding_router.get(
    "/providers",
    response_model=ProvidersListResponse,
)
async def list_providers() -> ProvidersListResponse:
    """List all available geocoding providers and their capabilities.

    Public endpoint — no authentication required.
    """
    settings = get_settings()
    metadata = get_all_provider_metadata(settings)

    providers_info = [
        ProviderInfo(
            name=m.name,
            service_type=m.service_type,
            requires_api_key=m.requires_api_key,
            is_configured=m.is_configured,
            rate_limit_delay=m.rate_limit_delay,
        )
        for m in metadata
    ]

    return ProvidersListResponse(
        providers=providers_info,
        fallback_order=settings.geocoder_fallback_order_list,
    )
