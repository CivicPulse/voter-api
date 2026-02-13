"""Geocoding service — orchestrates batch/single geocoding, manual entries, and primary designation."""

import asyncio
import uuid
from datetime import UTC, datetime

from geoalchemy2.shape import from_shape
from loguru import logger
from shapely.geometry import Point
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.geocoder import (
    cache_lookup,
    cache_store,
    get_geocoder,
    normalize_freeform_address,
    parse_address_components,
    reconstruct_address,
)
from voter_api.lib.geocoder.base import GeocodingProviderError, GeocodingResult
from voter_api.lib.geocoder.point_lookup import validate_georgia_coordinates
from voter_api.lib.geocoder.verify import validate_address_components
from voter_api.models.geocoded_location import GeocodedLocation
from voter_api.models.geocoder_cache import GeocoderCache
from voter_api.models.geocoding_job import GeocodingJob
from voter_api.models.voter import Voter
from voter_api.schemas.geocoding import (
    AddressGeocodeResponse,
    AddressVerifyResponse,
    GeocodeMetadata,
    MalformedComponent,
    ValidationDetail,
)
from voter_api.services.address_service import prefix_search, upsert_from_geocode

MAX_RETRIES = 3
RETRY_BASE_DELAY = 60.0  # seconds

# Provider name and timeout for single-address endpoint
_SINGLE_PROVIDER = "census"
_SINGLE_TIMEOUT = 2.0  # 2s per attempt, 4s total budget (2 attempts max) per FR-009
_SINGLE_MAX_ATTEMPTS = 2


async def geocode_single_address(
    session: AsyncSession,
    address_string: str,
) -> AddressGeocodeResponse | None:
    """Geocode a single freeform address string.

    Normalizes input, checks cache, calls provider on miss with retry
    (2 attempts, 2s timeout each, 4s total budget per FR-009), upserts
    address row and cache entry on success.

    Args:
        session: Database session.
        address_string: Raw freeform address from the consumer.

    Returns:
        AddressGeocodeResponse on success, None if provider returns no match.

    Raises:
        ValueError: If geocoded coordinates are outside Georgia.
        GeocodingProviderError: If provider fails after all retry attempts.
    """
    normalized = normalize_freeform_address(address_string)
    if not normalized:
        return None

    geocoder = get_geocoder(_SINGLE_PROVIDER)
    geocoder._timeout = _SINGLE_TIMEOUT  # Override to 2s for single-address path

    # Cache lookup
    cached = await cache_lookup(session, geocoder.provider_name, normalized)
    if cached:
        # Validate Georgia coordinates even for cached results
        validate_georgia_coordinates(cached.latitude, cached.longitude)

        formatted = cached.matched_address or normalized
        return AddressGeocodeResponse(
            formatted_address=formatted,
            latitude=cached.latitude,
            longitude=cached.longitude,
            confidence=cached.confidence_score,
            metadata=GeocodeMetadata(cached=True, provider=geocoder.provider_name),
        )

    # Cache miss — call provider with single retry (2 attempts max)
    last_error: GeocodingProviderError | None = None
    for attempt in range(_SINGLE_MAX_ATTEMPTS):
        try:
            result = await geocoder.geocode(normalized)
            break
        except GeocodingProviderError as e:
            last_error = e
            if attempt < _SINGLE_MAX_ATTEMPTS - 1:
                logger.debug(f"Single geocode retry {attempt + 1}/{_SINGLE_MAX_ATTEMPTS}: {e}")
                continue
            raise last_error from e
    else:
        # All attempts exhausted without success or exception
        return None

    if result is None:
        return None

    # Validate Georgia coordinates
    validate_georgia_coordinates(result.latitude, result.longitude)

    # Parse components and upsert Address row
    components = parse_address_components(normalized)
    address_row = await upsert_from_geocode(session, normalized, components.to_dict())

    # Store in cache with address_id FK
    await cache_store(session, geocoder.provider_name, normalized, result)
    # Update the cache entry with address_id
    cache_result = await session.execute(
        select(GeocoderCache).where(
            GeocoderCache.provider == geocoder.provider_name,
            GeocoderCache.normalized_address == normalized,
        )
    )
    cache_entry = cache_result.scalar_one_or_none()
    if cache_entry:
        cache_entry.address_id = address_row.id
        await session.flush()

    await session.commit()

    formatted = result.matched_address or normalized
    return AddressGeocodeResponse(
        formatted_address=formatted,
        latitude=result.latitude,
        longitude=result.longitude,
        confidence=result.confidence_score,
        metadata=GeocodeMetadata(cached=False, provider=geocoder.provider_name),
    )


async def verify_address(
    session: AsyncSession,
    address_string: str,
) -> AddressVerifyResponse:
    """Verify and autocomplete a freeform address.

    Normalizes input, parses components, validates completeness,
    and returns suggestions from the canonical address store.

    Args:
        session: Database session.
        address_string: Raw freeform address from the consumer.

    Returns:
        AddressVerifyResponse with validation and suggestions.
    """
    normalized = normalize_freeform_address(address_string)
    components = parse_address_components(address_string)
    feedback = validate_address_components(components)

    # Get suggestions if input is long enough
    suggestions = []
    if normalized and len(normalized) >= 5:
        suggestions = await prefix_search(session, normalized, limit=10)

    return AddressVerifyResponse(
        input_address=address_string,
        normalized_address=normalized,
        is_well_formed=feedback.is_well_formed,
        validation=ValidationDetail(
            present_components=feedback.present_components,
            missing_components=feedback.missing_components,
            malformed_components=[
                MalformedComponent(component=m.component, issue=m.issue) for m in feedback.malformed_components
            ],
        ),
        suggestions=suggestions,
    )


async def create_geocoding_job(
    session: AsyncSession,
    *,
    provider: str = "census",
    county: str | None = None,
    force_regeocode: bool = False,
    triggered_by: uuid.UUID | None = None,
) -> GeocodingJob:
    """Create a new geocoding job record.

    Args:
        session: Database session.
        provider: Geocoder provider name.
        county: Optional county filter.
        force_regeocode: Whether to re-geocode already geocoded voters.
        triggered_by: User ID who triggered the job.

    Returns:
        The created GeocodingJob.
    """
    job = GeocodingJob(
        provider=provider,
        county=county,
        force_regeocode=force_regeocode,
        status="pending",
        triggered_by=triggered_by,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def process_geocoding_job(
    session: AsyncSession,
    job: GeocodingJob,
    batch_size: int = 100,
    rate_limit: int = 5,
) -> GeocodingJob:
    """Process a batch geocoding job.

    Finds un-geocoded voters, reconstructs addresses, geocodes via provider
    with rate limiting and caching, and stores results.

    Args:
        session: Database session.
        job: The GeocodingJob to process.
        batch_size: Voters per processing batch.
        rate_limit: Max concurrent geocoding requests.

    Returns:
        The updated GeocodingJob with final counts.
    """
    job.status = "running"
    job.started_at = datetime.now(UTC)
    await session.commit()

    geocoder = get_geocoder(job.provider)
    semaphore = asyncio.Semaphore(rate_limit)

    succeeded = 0
    failed_count = 0
    cache_hits = 0
    processed = 0
    errors: list[dict] = []

    try:
        # Build voter query
        query = select(Voter).where(Voter.present_in_latest_import.is_(True))

        if job.county:
            query = query.where(Voter.county == job.county)

        if not job.force_regeocode:
            # Only voters without a geocoded location from this provider
            geocoded_voter_ids = (
                select(GeocodedLocation.voter_id).where(GeocodedLocation.source_type == job.provider).scalar_subquery()
            )
            query = query.where(~Voter.id.in_(geocoded_voter_ids))

        query = query.order_by(Voter.id)

        # Count total
        count_result = await session.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        job.total_records = total
        await session.commit()

        # Process in batches with offset-based pagination
        offset = job.last_processed_voter_offset or 0

        while offset < total:
            batch_query = query.offset(offset).limit(batch_size)
            result = await session.execute(batch_query)
            voters = list(result.scalars().all())

            if not voters:
                break

            for voter in voters:
                address = reconstruct_address(
                    street_number=voter.residence_street_number,
                    pre_direction=voter.residence_pre_direction,
                    street_name=voter.residence_street_name,
                    street_type=voter.residence_street_type,
                    post_direction=voter.residence_post_direction,
                    apt_unit=voter.residence_apt_unit_number,
                    city=voter.residence_city,
                    zipcode=voter.residence_zipcode,
                )

                if not address:
                    processed += 1
                    failed_count += 1
                    errors.append(
                        {
                            "voter_id": str(voter.id),
                            "error": "No address components available",
                        }
                    )
                    continue

                # Try cache first
                cached = await cache_lookup(session, geocoder.provider_name, address)
                if cached:
                    await _store_geocoded_location(session, voter, cached, geocoder.provider_name, address)
                    cache_hits += 1
                    succeeded += 1
                    processed += 1
                    continue

                # Geocode with rate limiting and retry
                geo_result = await _geocode_with_retry(geocoder, address, semaphore)

                if geo_result:
                    await cache_store(session, geocoder.provider_name, address, geo_result)
                    await _store_geocoded_location(session, voter, geo_result, geocoder.provider_name, address)
                    succeeded += 1
                else:
                    failed_count += 1
                    errors.append(
                        {
                            "voter_id": str(voter.id),
                            "error": "Geocoding returned no result",
                        }
                    )

                processed += 1

            await session.commit()

            offset += len(voters)
            job.last_processed_voter_offset = offset
            job.processed = processed
            job.succeeded = succeeded
            job.failed = failed_count
            job.cache_hits = cache_hits
            await session.commit()

        # Final update
        job.status = "completed"
        job.processed = processed
        job.succeeded = succeeded
        job.failed = failed_count
        job.cache_hits = cache_hits
        job.error_log = errors if errors else None
        job.completed_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            f"Geocoding completed: {processed} processed, {succeeded} succeeded, "
            f"{failed_count} failed, {cache_hits} cache hits"
        )

    except Exception:
        job.status = "failed"
        job.error_log = errors if errors else None
        await session.commit()
        raise

    return job


async def _geocode_with_retry(
    geocoder: object,
    address: str,
    semaphore: asyncio.Semaphore,
) -> GeocodingResult | None:
    """Geocode with rate limiting and exponential backoff retry.

    Catches GeocodingProviderError to maintain batch pipeline resilience —
    provider transport errors are logged and retried rather than aborting.

    Args:
        geocoder: Geocoder provider instance.
        address: Normalized address string.
        semaphore: Rate limiter.

    Returns:
        GeocodingResult or None after all retries exhausted.
    """
    for attempt in range(MAX_RETRIES):
        try:
            async with semaphore:
                result = await geocoder.geocode(address)  # type: ignore[union-attr]
                if result is not None:
                    return result
        except GeocodingProviderError as e:
            logger.warning(f"Batch geocode provider error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_BASE_DELAY * (2**attempt)
            logger.debug(f"Geocoding retry {attempt + 1}/{MAX_RETRIES} in {delay}s")
            await asyncio.sleep(delay)

    return None


async def _store_geocoded_location(
    session: AsyncSession,
    voter: Voter,
    result: GeocodingResult,
    source_type: str,
    input_address: str,
) -> GeocodedLocation:
    """Store a geocoded location for a voter, setting as primary if first.

    Args:
        session: Database session.
        voter: The voter record.
        result: Geocoding result.
        source_type: Provider name or manual/field-survey.
        input_address: The address that was geocoded.

    Returns:
        The created or updated GeocodedLocation.
    """
    point = from_shape(Point(result.longitude, result.latitude), srid=4326)

    # Check if voter has any existing geocoded location
    existing_count = await session.execute(select(func.count()).where(GeocodedLocation.voter_id == voter.id))
    is_first = existing_count.scalar_one() == 0

    # Check if this source already exists (for upsert on force_regeocode)
    existing = await session.execute(
        select(GeocodedLocation).where(
            GeocodedLocation.voter_id == voter.id,
            GeocodedLocation.source_type == source_type,
        )
    )
    location = existing.scalar_one_or_none()

    if location:
        location.latitude = result.latitude
        location.longitude = result.longitude
        location.point = point
        location.confidence_score = result.confidence_score
        location.input_address = input_address
        location.geocoded_at = datetime.now(UTC)
    else:
        location = GeocodedLocation(
            voter_id=voter.id,
            latitude=result.latitude,
            longitude=result.longitude,
            point=point,
            confidence_score=result.confidence_score,
            source_type=source_type,
            is_primary=is_first,
            input_address=input_address,
            geocoded_at=datetime.now(UTC),
        )
        session.add(location)

    await session.flush()
    return location


async def add_manual_location(
    session: AsyncSession,
    voter_id: uuid.UUID,
    latitude: float,
    longitude: float,
    source_type: str = "manual",
    set_as_primary: bool = False,
) -> GeocodedLocation:
    """Add a manually geocoded location for a voter.

    Args:
        session: Database session.
        voter_id: Voter ID.
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        source_type: Source type (manual or field-survey).
        set_as_primary: Whether to set as primary location.

    Returns:
        The created GeocodedLocation.
    """
    point = from_shape(Point(longitude, latitude), srid=4326)

    # Check if first location for this voter
    existing_count = await session.execute(select(func.count()).where(GeocodedLocation.voter_id == voter_id))
    is_first = existing_count.scalar_one() == 0

    location = GeocodedLocation(
        voter_id=voter_id,
        latitude=latitude,
        longitude=longitude,
        point=point,
        source_type=source_type,
        is_primary=is_first or set_as_primary,
        geocoded_at=datetime.now(UTC),
    )
    session.add(location)

    if set_as_primary and not is_first:
        await _set_primary(session, voter_id, location)

    await session.commit()
    await session.refresh(location)
    return location


async def set_primary_location(
    session: AsyncSession,
    voter_id: uuid.UUID,
    location_id: uuid.UUID,
) -> GeocodedLocation | None:
    """Set a geocoded location as the primary for a voter.

    Args:
        session: Database session.
        voter_id: Voter ID.
        location_id: GeocodedLocation ID to set as primary.

    Returns:
        The updated GeocodedLocation or None if not found.
    """
    result = await session.execute(
        select(GeocodedLocation).where(
            GeocodedLocation.id == location_id,
            GeocodedLocation.voter_id == voter_id,
        )
    )
    location = result.scalar_one_or_none()
    if location is None:
        return None

    await _set_primary(session, voter_id, location)
    await session.commit()
    await session.refresh(location)
    return location


async def _set_primary(
    session: AsyncSession,
    voter_id: uuid.UUID,
    location: GeocodedLocation,
) -> None:
    """Set one location as primary, unsetting all others for this voter."""
    await session.execute(
        update(GeocodedLocation).where(GeocodedLocation.voter_id == voter_id).values(is_primary=False)
    )
    location.is_primary = True
    await session.flush()


async def get_geocoding_job(session: AsyncSession, job_id: uuid.UUID) -> GeocodingJob | None:
    """Get a geocoding job by ID."""
    result = await session.execute(select(GeocodingJob).where(GeocodingJob.id == job_id))
    return result.scalar_one_or_none()


async def get_voter_locations(session: AsyncSession, voter_id: uuid.UUID) -> list[GeocodedLocation]:
    """Get all geocoded locations for a voter."""
    result = await session.execute(
        select(GeocodedLocation)
        .where(GeocodedLocation.voter_id == voter_id)
        .order_by(GeocodedLocation.is_primary.desc(), GeocodedLocation.geocoded_at.desc())
    )
    return list(result.scalars().all())


async def get_cache_stats(session: AsyncSession) -> list[dict]:
    """Get per-provider cache statistics."""
    result = await session.execute(
        select(
            GeocoderCache.provider,
            func.count(GeocoderCache.id).label("cached_count"),
            func.min(GeocoderCache.cached_at).label("oldest_entry"),
            func.max(GeocoderCache.cached_at).label("newest_entry"),
        ).group_by(GeocoderCache.provider)
    )
    return [
        {
            "provider": row.provider,
            "cached_count": row.cached_count,
            "oldest_entry": row.oldest_entry,
            "newest_entry": row.newest_entry,
        }
        for row in result.all()
    ]
