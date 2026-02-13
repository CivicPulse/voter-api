"""Address service — manages canonical address store operations."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.address import Address


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
