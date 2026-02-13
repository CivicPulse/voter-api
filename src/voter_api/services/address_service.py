"""Address service — manages canonical address store operations."""

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.lib.geocoder import (
    normalize_freeform_address,
    parse_address_components,
    reconstruct_address,
)
from voter_api.lib.geocoder.verify import BaseSuggestionSource
from voter_api.models.address import Address
from voter_api.models.geocoder_cache import GeocoderCache
from voter_api.models.voter import Voter
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


async def backfill_voter_addresses(
    session: AsyncSession,
    batch_size: int = 500,
) -> dict[str, int]:
    """Backfill voters with residence_address_id IS NULL.

    For each unlinked voter, reconstructs the address from inline components,
    normalizes it, parses components, upserts into the canonical addresses table,
    and sets the voter's residence_address_id FK.

    Idempotent and safe to re-run. Voters whose addresses cannot be reconstructed
    are skipped (FK stays NULL for manual review).

    Args:
        session: Database session.
        batch_size: Voters per processing batch.

    Returns:
        Dict with counts: linked, skipped, total.
    """
    linked = 0
    skipped = 0

    # Count total unlinked voters
    count_result = await session.execute(
        select(func.count()).where(
            Voter.residence_address_id.is_(None),
            Voter.present_in_latest_import.is_(True),
        )
    )
    total = count_result.scalar_one()

    if total == 0:
        logger.info("No unlinked voters to backfill")
        return {"linked": 0, "skipped": 0, "total": 0}

    logger.info(f"Backfilling {total} voters with residence_address_id")

    offset = 0
    while offset < total:
        query = (
            select(Voter)
            .where(
                Voter.residence_address_id.is_(None),
                Voter.present_in_latest_import.is_(True),
            )
            .order_by(Voter.id)
            .offset(offset)
            .limit(batch_size)
        )
        result = await session.execute(query)
        voters = list(result.scalars().all())

        if not voters:
            break

        for voter in voters:
            address_str = reconstruct_address(
                street_number=voter.residence_street_number,
                pre_direction=voter.residence_pre_direction,
                street_name=voter.residence_street_name,
                street_type=voter.residence_street_type,
                post_direction=voter.residence_post_direction,
                apt_unit=voter.residence_apt_unit_number,
                city=voter.residence_city,
                zipcode=voter.residence_zipcode,
            )

            if not address_str:
                skipped += 1
                continue

            normalized = normalize_freeform_address(address_str)
            if not normalized:
                skipped += 1
                continue

            components = parse_address_components(normalized)
            try:
                address_row = await upsert_from_geocode(session, normalized, components.to_dict())
                voter.residence_address_id = address_row.id
                linked += 1
            except Exception:
                logger.warning(f"Failed to upsert address for voter {voter.id}")
                skipped += 1

        await session.commit()
        offset += len(voters)
        logger.debug(f"Backfill progress: {offset}/{total} processed, {linked} linked, {skipped} skipped")

    logger.info(f"Backfill complete: {linked} linked, {skipped} skipped out of {total}")
    return {"linked": linked, "skipped": skipped, "total": total}


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
