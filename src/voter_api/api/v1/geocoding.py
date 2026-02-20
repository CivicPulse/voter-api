"""Geocoding API endpoints — single-address geocode, point lookup, verify, batch, and cache."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.background import task_runner
from voter_api.core.dependencies import get_async_session, get_current_user, require_role
from voter_api.lib.geocoder.base import GeocodingProviderError
from voter_api.lib.geocoder.point_lookup import validate_georgia_coordinates
from voter_api.models.user import User
from voter_api.schemas.geocoding import (
    AddressGeocodeResponse,
    AddressVerifyResponse,
    BatchGeocodingRequest,
    CacheStatsResponse,
    DistrictInfo,
    GeocodedLocationResponse,
    GeocodingJobResponse,
    PointLookupResponse,
    ProviderGeocodeResult,
    VoterGeocodeAllResponse,
)
from voter_api.services.boundary_service import find_boundaries_at_point
from voter_api.services.geocoding_service import (
    create_geocoding_job,
    geocode_single_address,
    geocode_voter_all_providers,
    get_cache_stats,
    get_geocoding_job,
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
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> AddressVerifyResponse:
    """Verify and autocomplete a freeform address."""
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
    _current_user: User = Depends(get_current_user),  # noqa: B008
) -> PointLookupResponse:
    """Look up boundary districts for a geographic point."""
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
    _current_user: User = Depends(get_current_user),  # noqa: B008
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
    except GeocodingProviderError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Geocoding provider is temporarily unavailable. Please retry later.",
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

    # Run geocoding in background
    async def _run_geocoding() -> None:
        from voter_api.core.database import get_session_factory

        factory = get_session_factory()
        async with factory() as bg_session:
            bg_job = await get_geocoding_job(bg_session, job.id)
            if bg_job:
                await process_geocoding_job(bg_session, bg_job)
            else:
                logger.error(f"Background geocoding job {job.id} not found")

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
