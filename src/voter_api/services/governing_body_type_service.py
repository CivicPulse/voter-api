"""Governing body type service -- CRUD for the type lookup table."""

import re

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.governing_body_type import GoverningBodyType


async def list_types(session: AsyncSession) -> list[GoverningBodyType]:
    """Return all governing body types ordered by name.

    Args:
        session: Database session.

    Returns:
        List of all governing body types.
    """
    result = await session.execute(select(GoverningBodyType).order_by(GoverningBodyType.name))
    types = list(result.scalars().all())
    logger.info(f"Listed {len(types)} governing body types")
    return types


async def create_type(
    session: AsyncSession,
    *,
    name: str,
    description: str | None = None,
) -> GoverningBodyType:
    """Create a new governing body type with auto-generated slug.

    The slug is derived from the name: lowercased, spaces replaced with
    hyphens, and special characters stripped.

    Args:
        session: Database session.
        name: Display name for the type.
        description: Optional description.

    Returns:
        The created GoverningBodyType.

    Raises:
        ValueError: If a type with the same name or slug already exists.
    """
    slug = _generate_slug(name)
    body_type = GoverningBodyType(
        name=name,
        slug=slug,
        description=description,
        is_default=False,
    )
    session.add(body_type)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        msg = f"Governing body type with name '{name}' or slug '{slug}' already exists"
        raise ValueError(msg) from None
    await session.refresh(body_type)
    logger.info(f"Created governing body type {body_type.id} ({name}, slug={slug})")
    return body_type


def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from a display name.

    Args:
        name: The display name to slugify.

    Returns:
        Lowercase slug with hyphens replacing spaces and special chars stripped.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug.strip("-")
