"""Attachments API endpoints — upload, download, list, and soft-delete."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.config import Settings, get_settings
from voter_api.core.dependencies import get_async_session, require_role
from voter_api.lib.meetings.storage import LocalFileStorage
from voter_api.models.user import User
from voter_api.schemas.meeting_attachment import (
    AttachmentListResponse,
    AttachmentResponse,
)
from voter_api.services.agenda_item_service import require_agenda_item_in_meeting
from voter_api.services.meeting_attachment_service import (
    delete_attachment,
    download_attachment,
    get_attachment,
    list_attachments,
    upload_attachment,
)

attachments_router = APIRouter(tags=["attachments"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_storage(settings: Settings = Depends(get_settings)) -> LocalFileStorage:
    return LocalFileStorage(settings.meeting_upload_dir)


def _response_from_attachment(attachment: object) -> AttachmentResponse:
    resp = AttachmentResponse.model_validate(attachment)
    resp.download_url = f"/api/v1/attachments/{resp.id}/download"
    return resp


async def _handle_upload(
    file: UploadFile,
    session: AsyncSession,
    storage: LocalFileStorage,
    current_user: User,
    max_file_size_bytes: int,
    meeting_id: uuid.UUID | None = None,
    agenda_item_id: uuid.UUID | None = None,
) -> AttachmentResponse:
    content = await file.read()
    if len(content) > max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {max_file_size_bytes // (1024 * 1024)} MB",
        )
    try:
        attachment = await upload_attachment(
            session,
            file_content=content,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            meeting_id=meeting_id,
            agenda_item_id=agenda_item_id,
            storage=storage,
            max_file_size_bytes=max_file_size_bytes,
        )
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg) from e
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_msg,
        ) from e
    logger.info(f"User {current_user.username} uploaded attachment {attachment.id}")
    return _response_from_attachment(attachment)


# ---------------------------------------------------------------------------
# Meeting-level attachments
# ---------------------------------------------------------------------------


@attachments_router.get(
    "/meetings/{meeting_id}/attachments",
    response_model=AttachmentListResponse,
)
async def list_meeting_attachments(
    meeting_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> AttachmentListResponse:
    """List attachments for a meeting."""
    attachments = await list_attachments(session, meeting_id=meeting_id)
    return AttachmentListResponse(items=[_response_from_attachment(a) for a in attachments])


@attachments_router.post(
    "/meetings/{meeting_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_meeting_attachment(
    meeting_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
    storage: LocalFileStorage = Depends(_get_storage),
    settings: Settings = Depends(get_settings),
) -> AttachmentResponse:
    """Upload a file attachment to a meeting."""
    max_file_size_bytes = settings.meeting_max_file_size_mb * 1024 * 1024
    return await _handle_upload(file, session, storage, current_user, max_file_size_bytes, meeting_id=meeting_id)


# ---------------------------------------------------------------------------
# Agenda item-level attachments
# ---------------------------------------------------------------------------


@attachments_router.get(
    "/meetings/{meeting_id}/agenda-items/{agenda_item_id}/attachments",
    response_model=AttachmentListResponse,
)
async def list_agenda_item_attachments(
    meeting_id: uuid.UUID,
    agenda_item_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> AttachmentListResponse:
    """List attachments for an agenda item."""
    try:
        await require_agenda_item_in_meeting(session, meeting_id, agenda_item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    attachments = await list_attachments(session, agenda_item_id=agenda_item_id)
    return AttachmentListResponse(items=[_response_from_attachment(a) for a in attachments])


@attachments_router.post(
    "/meetings/{meeting_id}/agenda-items/{agenda_item_id}/attachments",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_agenda_item_attachment(
    meeting_id: uuid.UUID,
    agenda_item_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin", "contributor")),
    storage: LocalFileStorage = Depends(_get_storage),
    settings: Settings = Depends(get_settings),
) -> AttachmentResponse:
    """Upload a file attachment to an agenda item."""
    try:
        await require_agenda_item_in_meeting(session, meeting_id, agenda_item_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    max_file_size_bytes = settings.meeting_max_file_size_mb * 1024 * 1024
    return await _handle_upload(
        file, session, storage, current_user, max_file_size_bytes, agenda_item_id=agenda_item_id
    )


# ---------------------------------------------------------------------------
# Direct attachment access (by attachment ID)
# ---------------------------------------------------------------------------


@attachments_router.get(
    "/attachments/{attachment_id}",
    response_model=AttachmentResponse,
)
async def get_attachment_detail(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
) -> AttachmentResponse:
    """Get attachment metadata."""
    attachment = await get_attachment(session, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return _response_from_attachment(attachment)


@attachments_router.get(
    "/attachments/{attachment_id}/download",
)
async def download_attachment_file(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(require_role("admin", "analyst", "viewer", "contributor")),
    storage: LocalFileStorage = Depends(_get_storage),
) -> Response:
    """Download an attachment file with proper Content-Disposition."""
    try:
        content, attachment = await download_attachment(session, attachment_id, storage)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    safe_name = re.sub(r'[\x00-\x1f\x7f"\\]', "_", attachment.original_filename)
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )


@attachments_router.delete(
    "/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment_endpoint(
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(require_role("admin")),
) -> None:
    """Soft-delete an attachment (file preserved on disk)."""
    try:
        await delete_attachment(session, attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    logger.info(f"Admin {current_user.username} deleted attachment {attachment_id}")
