"""Per-provider database caching layer for geocoding results."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.geocoder.base import GeocodingResult
from voter_api.models.geocoder_cache import GeocoderCache


async def cache_lookup(
    session: AsyncSession,
    provider: str,
    normalized_address: str,
) -> GeocodingResult | None:
    """Look up a cached geocoding result.

    Args:
        session: Database session.
        provider: Provider name.
        normalized_address: Normalized address string (cache key).

    Returns:
        GeocodingResult if found, None on cache miss.
    """
    result = await session.execute(
        select(GeocoderCache).where(
            GeocoderCache.provider == provider,
            GeocoderCache.normalized_address == normalized_address,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    return GeocodingResult(
        latitude=entry.latitude,
        longitude=entry.longitude,
        confidence_score=entry.confidence_score,
        raw_response=entry.raw_response,
        matched_address=entry.matched_address,
    )


async def cache_store(
    session: AsyncSession,
    provider: str,
    normalized_address: str,
    result: GeocodingResult,
    *,
    address_id: uuid.UUID | None = None,
) -> None:
    """Store a geocoding result in the cache.

    Args:
        session: Database session.
        provider: Provider name.
        normalized_address: Normalized address string (cache key).
        result: Geocoding result to cache.
        address_id: Optional FK to the canonical address record.
    """
    entry = GeocoderCache(
        provider=provider,
        normalized_address=normalized_address,
        latitude=result.latitude,
        longitude=result.longitude,
        confidence_score=result.confidence_score,
        raw_response=result.raw_response,
        matched_address=result.matched_address,
        address_id=address_id,
        cached_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.flush()
