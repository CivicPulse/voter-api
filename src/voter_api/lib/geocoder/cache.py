"""Per-provider database caching layer for geocoding results."""

import contextlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.geocoder.base import GeocodeQuality, GeocodingResult
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

    # Recover quality from raw_response metadata if stored
    quality = None
    if entry.raw_response and "_quality" in entry.raw_response:
        with contextlib.suppress(ValueError):
            quality = GeocodeQuality(entry.raw_response["_quality"])

    return GeocodingResult(
        latitude=entry.latitude,
        longitude=entry.longitude,
        confidence_score=entry.confidence_score,
        raw_response=entry.raw_response,
        matched_address=entry.matched_address,
        quality=quality,
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
    # Embed quality in raw_response for cache round-tripping (avoids migration)
    raw = result.raw_response
    if result.quality is not None:
        raw = dict(raw) if raw else {}
        raw["_quality"] = result.quality.value

    entry = GeocoderCache(
        provider=provider,
        normalized_address=normalized_address,
        latitude=result.latitude,
        longitude=result.longitude,
        confidence_score=result.confidence_score,
        raw_response=raw,
        matched_address=result.matched_address,
        address_id=address_id,
        cached_at=datetime.now(UTC),
    )
    session.add(entry)
    await session.flush()
