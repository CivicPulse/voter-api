"""Governing body types API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from voter_api.core.dependencies import get_async_session, require_role
from voter_api.models.user import User
from voter_api.schemas.governing_body_type import (
    GoverningBodyTypeCreateRequest,
    GoverningBodyTypeResponse,
)
from voter_api.services.governing_body_type_service import (
    create_type,
    list_types,
)

governing_body_types_router = APIRouter(
    prefix="/governing-body-types",
    tags=["governing-body-types"],
)


@governing_body_types_router.get(
    "",
)
async def list_all_types(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    _user: Annotated[User, Depends(require_role("admin", "analyst", "viewer", "contributor"))],
) -> dict:
    """List all governing body types.

    Requires authentication (any role).
    """
    try:
        types = await list_types(session)
    except Exception as e:
        logger.error(f"Unexpected error listing governing body types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error listing governing body types.",
        ) from e
    return {"items": [GoverningBodyTypeResponse.model_validate(t) for t in types]}


@governing_body_types_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_type_endpoint(
    body: GoverningBodyTypeCreateRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
    current_user: Annotated[User, Depends(require_role("admin"))],
) -> GoverningBodyTypeResponse:
    """Create a new governing body type.

    Requires admin authentication. The slug is auto-generated from the name.
    """
    try:
        body_type = await create_type(
            session,
            name=body.name,
            description=body.description,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Unexpected error creating governing body type: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error creating governing body type.",
        ) from e
    logger.info(f"Admin {current_user.username} created governing body type {body_type.id}")
    return GoverningBodyTypeResponse.model_validate(body_type)
