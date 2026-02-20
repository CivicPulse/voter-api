"""Agenda items API endpoints with gap-based ordering and reorder support."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.agenda_item import (
    AgendaItemCreateRequest,
    AgendaItemListResponse,
    AgendaItemReorderRequest,
    AgendaItemResponse,
    AgendaItemUpdateRequest,
)
from voter_api.services.agenda_item_service import (
    create_item,
    delete_item,
    get_item,
    get_item_child_counts,
    list_items,
    reorder_items,
    update_item,
)

agenda_items_router = APIRouter(
    prefix="/meetings/{meeting_id}/agenda-items",
    tags=["agenda-items"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _response_from_item(session: AsyncSession, item: object) -> AgendaItemResponse:
    """Build a response with child counts."""
    resp = AgendaItemResponse.model_validate(item)
    attachment_count, video_count = await get_item_child_counts(session, resp.id)
    resp.attachment_count = attachment_count
    resp.video_embed_count = video_count
    return resp


# ---------------------------------------------------------------------------
# List (fixed-prefix routes FIRST)
# ---------------------------------------------------------------------------


@agenda_items_router.get(
    "",
    response_model=AgendaItemListResponse,
)
async def list_agenda_items(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> AgendaItemListResponse:
    """List all agenda items for a meeting, ordered by display_order."""
    try:
        items = await list_items(session, meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    responses = [await _response_from_item(session, item) for item in items]
    return AgendaItemListResponse(items=responses)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@agenda_items_router.post(
    "",
    response_model=AgendaItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agenda_item(
    meeting_id: uuid.UUID,
    body: AgendaItemCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> AgendaItemResponse:
    """Create a new agenda item. Appended to end if display_order omitted."""
    try:
        item = await create_item(session, meeting_id=meeting_id, data=body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"User {current_user.username} created agenda item {item.id}")
    return await _response_from_item(session, item)


# ---------------------------------------------------------------------------
# Reorder (fixed-prefix, before /{item_id})
# ---------------------------------------------------------------------------


@agenda_items_router.put(
    "/reorder",
    response_model=AgendaItemListResponse,
)
async def reorder_agenda_items(
    meeting_id: uuid.UUID,
    body: AgendaItemReorderRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> AgendaItemListResponse:
    """Bulk reorder agenda items by providing an ordered list of item IDs."""
    try:
        items = await reorder_items(session, meeting_id, body.item_ids)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg) from e
    logger.info(f"User {current_user.username} reordered agenda items for meeting {meeting_id}")
    responses = [await _response_from_item(session, item) for item in items]
    return AgendaItemListResponse(items=responses)


# ---------------------------------------------------------------------------
# Parameterized routes (/{item_id} paths AFTER fixed-prefix routes)
# ---------------------------------------------------------------------------


@agenda_items_router.get(
    "/{item_id}",
    response_model=AgendaItemResponse,
)
async def get_agenda_item(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> AgendaItemResponse:
    """Get agenda item detail with child counts."""
    item = await get_item(session, meeting_id, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agenda item not found",
        )
    return await _response_from_item(session, item)


@agenda_items_router.patch(
    "/{item_id}",
    response_model=AgendaItemResponse,
)
async def update_agenda_item(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    body: AgendaItemUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> AgendaItemResponse:
    """Update an agenda item. Only provided fields are updated."""
    try:
        item = await update_item(session, meeting_id, item_id, data=body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"User {current_user.username} updated agenda item {item_id}")
    return await _response_from_item(session, item)


@agenda_items_router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agenda_item(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> None:
    """Soft-delete an agenda item and cascade to children."""
    try:
        await delete_item(session, meeting_id, item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"Admin {current_user.username} deleted agenda item {item_id}")
