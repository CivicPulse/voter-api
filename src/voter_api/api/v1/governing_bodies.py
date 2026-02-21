"""Governing bodies API endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.common import PaginationMeta
from voter_api.schemas.governing_body import (
    GoverningBodyCreateRequest,
    GoverningBodyDetailResponse,
    GoverningBodySummaryResponse,
    GoverningBodyUpdateRequest,
    PaginatedGoverningBodyResponse,
)
from voter_api.services.governing_body_service import (
    create_body,
    delete_body,
    get_body,
    get_meeting_count,
    list_bodies,
    update_body,
)

governing_bodies_router = APIRouter(
    prefix="/governing-bodies",
    tags=["governing-bodies"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_detail_response(
    session: AsyncSession,
    body: object,
) -> GoverningBodyDetailResponse:
    """Build a detail response with computed meeting_count.

    Args:
        session: Database session.
        body: The GoverningBody ORM instance.

    Returns:
        GoverningBodyDetailResponse with meeting_count populated.
    """
    meeting_count = await get_meeting_count(session, body.id)  # type: ignore[attr-defined]
    data = GoverningBodyDetailResponse.model_validate(body)
    data.meeting_count = meeting_count
    return data


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@governing_bodies_router.get(
    "",
)
async def list_all_bodies(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
    type_id: Annotated[uuid.UUID | None, Query(description="Filter by governing body type ID")] = None,
    jurisdiction: Annotated[str | None, Query(description="Filter by jurisdiction (partial match)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedGoverningBodyResponse:
    """List governing bodies with optional filters.

    Requires authentication (any role).
    """
    try:
        bodies, total = await list_bodies(
            session,
            type_id=type_id,
            jurisdiction=jurisdiction,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Unexpected error listing governing bodies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error listing governing bodies.",
        ) from e
    return PaginatedGoverningBodyResponse(
        items=[GoverningBodySummaryResponse.model_validate(b) for b in bodies],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        ),
    )


# ---------------------------------------------------------------------------
# Admin write endpoints
# ---------------------------------------------------------------------------


@governing_bodies_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_body_endpoint(
    body: GoverningBodyCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> GoverningBodyDetailResponse:
    """Create a new governing body.

    Requires admin authentication.
    """
    # Convert HttpUrl to string for storage
    website_url = str(body.website_url) if body.website_url is not None else None
    try:
        governing_body = await create_body(
            session,
            name=body.name,
            type_id=body.type_id,
            jurisdiction=body.jurisdiction,
            description=body.description,
            website_url=website_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error creating governing body: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error creating governing body.",
        ) from e
    logger.info(f"Admin {current_user.username} created governing body {governing_body.id}")
    return await _build_detail_response(session, governing_body)


# ---------------------------------------------------------------------------
# Parameterized routes (/{body_id} paths AFTER fixed-prefix routes)
# ---------------------------------------------------------------------------


@governing_bodies_router.get(
    "/{body_id}",
)
async def get_body_detail(
    body_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
) -> GoverningBodyDetailResponse:
    """Get governing body detail including meeting count.

    Requires authentication (any role).
    """
    try:
        governing_body = await get_body(session, body_id)
    except Exception as e:
        logger.error(f"Unexpected error fetching governing body {body_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error fetching governing body.",
        ) from e
    if governing_body is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Governing body not found",
        )
    return await _build_detail_response(session, governing_body)


@governing_bodies_router.patch(
    "/{body_id}",
)
async def update_body_endpoint(
    body_id: uuid.UUID,
    body: GoverningBodyUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> GoverningBodyDetailResponse:
    """Update a governing body.

    Requires admin authentication. Only provided fields are updated.
    """
    try:
        updates = body.model_dump(exclude_unset=True)
        # Convert HttpUrl to string for storage
        if "website_url" in updates and updates["website_url"] is not None:
            updates["website_url"] = str(updates["website_url"])
        governing_body = await update_body(session, body_id, data=updates)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error updating governing body {body_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error updating governing body.",
        ) from e
    logger.info(f"Admin {current_user.username} updated governing body {governing_body.id}")
    return await _build_detail_response(session, governing_body)


@governing_bodies_router.delete(
    "/{body_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_body_endpoint(
    body_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> None:
    """Soft-delete a governing body.

    Requires admin authentication. Refuses if the body has active meetings.
    """
    try:
        await delete_body(session, body_id)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error_msg) from e
    except Exception as e:
        logger.error(f"Unexpected error deleting governing body {body_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error deleting governing body.",
        ) from e
    logger.info(f"Admin {current_user.username} deleted governing body {body_id}")
