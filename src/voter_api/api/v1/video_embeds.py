"""Video embeds API endpoints — CRUD for meeting and agenda item video links."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.meeting_video_embed import (
    VideoEmbedCreateRequest,
    VideoEmbedListResponse,
    VideoEmbedResponse,
    VideoEmbedUpdateRequest,
)
from voter_api.services.agenda_item_service import require_agenda_item_in_meeting
from voter_api.services.meeting_video_embed_service import (
    create_embed,
    delete_embed,
    get_embed,
    list_embeds,
    update_embed,
)

video_embeds_router = APIRouter(tags=["video-embeds"])


# ---------------------------------------------------------------------------
# Meeting-level video embeds
# ---------------------------------------------------------------------------


@video_embeds_router.get(
    "/meetings/{meeting_id}/video-embeds",
    response_model=VideoEmbedListResponse,
)
async def list_meeting_video_embeds(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> VideoEmbedListResponse:
    """List video embeds for a meeting."""
    embeds = await list_embeds(session, meeting_id=meeting_id)
    return VideoEmbedListResponse(items=[VideoEmbedResponse.model_validate(e) for e in embeds])


@video_embeds_router.post(
    "/meetings/{meeting_id}/video-embeds",
    response_model=VideoEmbedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_meeting_video_embed(
    meeting_id: uuid.UUID,
    body: VideoEmbedCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> VideoEmbedResponse:
    """Add a video embed to a meeting."""
    try:
        embed = await create_embed(session, data=body.model_dump(), meeting_id=meeting_id)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg) from e
    logger.info(f"User {current_user.username} created video embed {embed.id}")
    return VideoEmbedResponse.model_validate(embed)


# ---------------------------------------------------------------------------
# Agenda item-level video embeds
# ---------------------------------------------------------------------------


@video_embeds_router.get(
    "/meetings/{meeting_id}/agenda-items/{agenda_item_id}/video-embeds",
    response_model=VideoEmbedListResponse,
)
async def list_agenda_item_video_embeds(
    meeting_id: uuid.UUID,
    agenda_item_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> VideoEmbedListResponse:
    """List video embeds for an agenda item."""
    try:
        await require_agenda_item_in_meeting(session, meeting_id, agenda_item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    embeds = await list_embeds(session, agenda_item_id=agenda_item_id)
    return VideoEmbedListResponse(items=[VideoEmbedResponse.model_validate(e) for e in embeds])


@video_embeds_router.post(
    "/meetings/{meeting_id}/agenda-items/{agenda_item_id}/video-embeds",
    response_model=VideoEmbedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agenda_item_video_embed(
    meeting_id: uuid.UUID,
    agenda_item_id: uuid.UUID,
    body: VideoEmbedCreateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> VideoEmbedResponse:
    """Add a video embed to an agenda item."""
    try:
        await require_agenda_item_in_meeting(session, meeting_id, agenda_item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    try:
        embed = await create_embed(session, data=body.model_dump(), agenda_item_id=agenda_item_id)
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg) from e
    logger.info(f"User {current_user.username} created video embed {embed.id}")
    return VideoEmbedResponse.model_validate(embed)


# ---------------------------------------------------------------------------
# Direct video embed access (by embed ID)
# ---------------------------------------------------------------------------


@video_embeds_router.get(
    "/video-embeds/{embed_id}",
    response_model=VideoEmbedResponse,
)
async def get_video_embed_detail(
    embed_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> VideoEmbedResponse:
    """Get video embed details."""
    embed = await get_embed(session, embed_id)
    if embed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video embed not found")
    return VideoEmbedResponse.model_validate(embed)


@video_embeds_router.patch(
    "/video-embeds/{embed_id}",
    response_model=VideoEmbedResponse,
)
async def update_video_embed_endpoint(
    embed_id: uuid.UUID,
    body: VideoEmbedUpdateRequest,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
) -> VideoEmbedResponse:
    """Update a video embed."""
    try:
        embed = await update_embed(session, embed_id, data=body.model_dump(exclude_unset=True))
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_msg) from e
    logger.info(f"User {current_user.username} updated video embed {embed_id}")
    return VideoEmbedResponse.model_validate(embed)


@video_embeds_router.delete(
    "/video-embeds/{embed_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_video_embed_endpoint(
    embed_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> None:
    """Soft-delete a video embed."""
    try:
        await delete_embed(session, embed_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"Admin {current_user.username} deleted video embed {embed_id}")
