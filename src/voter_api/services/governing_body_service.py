"""Governing body service -- CRUD with soft delete and meeting-count support."""

import uuid
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.models.governing_body import GoverningBody
from voter_api.models.meeting import Meeting

# Fields that may be set via the update endpoint.  Anything outside this set
# is silently ignored, preventing mass-assignment of internal fields such as
# ``deleted_at`` or ``id``.
_UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "type_id",
        "jurisdiction",
        "description",
        "website_url",
    }
)


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


async def list_bodies(
    session: AsyncSession,
    *,
    type_id: uuid.UUID | None = None,
    jurisdiction: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[GoverningBody], int]:
    """List governing bodies with optional filters.

    Args:
        session: Database session.
        type_id: Filter by governing body type ID.
        jurisdiction: Filter by jurisdiction (case-insensitive partial match).
        page: Page number (1-based).
        page_size: Items per page.

    Returns:
        Tuple of (governing bodies, total count).
    """
    base_filter = GoverningBody.deleted_at.is_(None)

    query = select(GoverningBody).where(base_filter)
    count_query = select(func.count(GoverningBody.id)).where(base_filter)

    if type_id is not None:
        query = query.where(GoverningBody.type_id == type_id)
        count_query = count_query.where(GoverningBody.type_id == type_id)
    if jurisdiction is not None:
        pattern = f"%{jurisdiction}%"
        query = query.where(GoverningBody.jurisdiction.ilike(pattern))
        count_query = count_query.where(GoverningBody.jurisdiction.ilike(pattern))

    total = (await session.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(GoverningBody.name).offset(offset).limit(page_size)
    result = await session.execute(query)
    bodies = list(result.scalars().all())

    logger.info(f"Listed {len(bodies)} governing bodies (total={total}, page={page})")
    return bodies, total


async def get_body(session: AsyncSession, body_id: uuid.UUID) -> GoverningBody | None:
    """Get a single governing body by ID (excluding soft-deleted).

    Args:
        session: Database session.
        body_id: The governing body UUID.

    Returns:
        The GoverningBody or None if not found / soft-deleted.
    """
    result = await session.execute(
        select(GoverningBody).where(
            GoverningBody.id == body_id,
            GoverningBody.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def get_meeting_count(session: AsyncSession, body_id: uuid.UUID) -> int:
    """Count active (non-deleted) meetings for a governing body.

    Args:
        session: Database session.
        body_id: The governing body UUID.

    Returns:
        Number of active meetings.
    """
    result = await session.execute(
        select(func.count(Meeting.id)).where(
            Meeting.governing_body_id == body_id,
            Meeting.deleted_at.is_(None),
        )
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Write operations (admin)
# ---------------------------------------------------------------------------


async def create_body(
    session: AsyncSession,
    *,
    name: str,
    type_id: uuid.UUID,
    jurisdiction: str,
    description: str | None = None,
    website_url: str | None = None,
) -> GoverningBody:
    """Create a new governing body.

    Args:
        session: Database session.
        name: Official name of the governing body.
        type_id: FK to governing_body_types.
        jurisdiction: Geographic jurisdiction.
        description: Optional description.
        website_url: Official website URL.

    Returns:
        The created GoverningBody.

    Raises:
        ValueError: If a duplicate (name, jurisdiction) already exists.
    """
    body = GoverningBody(
        name=name,
        type_id=type_id,
        jurisdiction=jurisdiction,
        description=description,
        website_url=website_url,
    )
    session.add(body)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        msg = f"Governing body '{name}' already exists for jurisdiction '{jurisdiction}'"
        raise ValueError(msg) from None
    await session.refresh(body)
    logger.info(f"Created governing body {body.id} ({name}, {jurisdiction})")
    return body


async def update_body(
    session: AsyncSession,
    body_id: uuid.UUID,
    *,
    data: dict,
) -> GoverningBody:
    """Update a governing body with the given fields.

    Args:
        session: Database session.
        body_id: The governing body UUID.
        data: Dict of field_name -> new_value. Only allowlisted fields
            are applied.

    Returns:
        The updated GoverningBody.

    Raises:
        ValueError: If the governing body is not found or soft-deleted.
    """
    body = await get_body(session, body_id)
    if body is None:
        msg = f"Governing body {body_id} not found"
        raise ValueError(msg)

    for field_name, value in data.items():
        if field_name in _UPDATABLE_FIELDS:
            setattr(body, field_name, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        msg = "Update would create a duplicate governing body"
        raise ValueError(msg) from None
    await session.refresh(body)
    logger.info(f"Updated governing body {body.id}")
    return body


async def delete_body(session: AsyncSession, body_id: uuid.UUID) -> None:
    """Soft-delete a governing body.

    Checks for active (non-deleted) meetings before deleting. If any
    exist, the deletion is refused.

    Args:
        session: Database session.
        body_id: The governing body UUID.

    Raises:
        ValueError: If the governing body is not found, already deleted,
            or has active meetings.
    """
    body = await get_body(session, body_id)
    if body is None:
        msg = f"Governing body {body_id} not found"
        raise ValueError(msg)

    meeting_count = await get_meeting_count(session, body_id)
    if meeting_count > 0:
        msg = "Cannot delete governing body with active meetings"
        raise ValueError(msg)

    body.deleted_at = datetime.now(UTC)
    await session.commit()
    logger.info(f"Soft-deleted governing body {body.id}")
