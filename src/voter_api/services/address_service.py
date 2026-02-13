"""Address service — manages canonical address store operations."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.geocoder.verify import BaseSuggestionSource
from voter_api.models.address import Address
from voter_api.models.geocoder_cache import GeocoderCache
from voter_api.schemas.geocoding import AddressSuggestion


async def upsert_from_geocode(
    session: AsyncSession,
    normalized_address: str,
    components: dict[str, str | None],
) -> Address:
    """Upsert an address row from a successful geocode result.

    ON CONFLICT (normalized_address) DO UPDATE SET updated_at = now().

    Args:
        session: Database session.
        normalized_address: Normalized address string (unique key).
        components: Parsed address component dict (from AddressComponents.to_dict()).

    Returns:
        The upserted Address row.
    """
    stmt = (
        pg_insert(Address)
        .values(
            normalized_address=normalized_address,
            **{k: v for k, v in components.items() if v is not None},
        )
        .on_conflict_do_update(
            constraint="uq_address_normalized",
            set_={"updated_at": Address.updated_at.default.arg},
        )
        .returning(Address)
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.scalar_one()


async def get_by_normalized(
    session: AsyncSession,
    normalized_address: str,
) -> Address | None:
    """Look up an address by its normalized string.

    Args:
        session: Database session.
        normalized_address: Normalized address string to find.

    Returns:
        Address or None if not found.
    """
    result = await session.execute(select(Address).where(Address.normalized_address == normalized_address))
    return result.scalar_one_or_none()


async def prefix_search(
    session: AsyncSession,
    normalized_prefix: str,
    limit: int = 10,
) -> list[AddressSuggestion]:
    """Search the canonical address store by prefix.

    Uses LIKE prefix% with text_pattern_ops index. JOINs geocoder_cache
    for coordinates and confidence_score, picking the highest-confidence
    provider result per address via DISTINCT ON.

    Args:
        session: Database session.
        normalized_prefix: Normalized address prefix to match.
        limit: Maximum results (default 10).

    Returns:
        List of AddressSuggestion with address, lat, lng, confidence.
    """
    # Use DISTINCT ON to get one row per address with highest confidence
    stmt = (
        select(
            Address.normalized_address,
            GeocoderCache.latitude,
            GeocoderCache.longitude,
            GeocoderCache.confidence_score,
        )
        .join(GeocoderCache, GeocoderCache.address_id == Address.id)
        .where(Address.normalized_address.like(f"{normalized_prefix}%"))
        .order_by(Address.normalized_address, GeocoderCache.confidence_score.desc().nullslast())
        .distinct(Address.normalized_address)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        AddressSuggestion(
            address=row.normalized_address,
            latitude=row.latitude,
            longitude=row.longitude,
            confidence_score=row.confidence_score,
        )
        for row in rows
    ]


class CacheSuggestionSource(BaseSuggestionSource):
    """Suggestion source backed by the canonical address store.

    Wraps prefix_search() to provide suggestions from cached/geocoded addresses.
    Lives in the service layer per Constitution Principle I.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search(self, query: str, limit: int = 10) -> list[AddressSuggestion]:
        """Search for address suggestions matching a prefix.

        Args:
            query: Normalized address prefix.
            limit: Maximum results.

        Returns:
            List of AddressSuggestion.
        """
        return await prefix_search(self._session, query, limit)
