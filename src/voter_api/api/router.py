"""Root API router with /api/v1 prefix and middleware registration."""

from fastapi import APIRouter, FastAPI

from voter_api.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, setup_cors
from voter_api.core.config import Settings


def create_router(settings: Settings) -> APIRouter:
    """Create the root API router with all sub-routers included.

    Args:
        settings: Application settings.

    Returns:
        Configured API router.
    """
    from voter_api.api.v1.agenda_items import agenda_items_router
    from voter_api.api.v1.analysis import analysis_router
    from voter_api.api.v1.attachments import attachments_router
    from voter_api.api.v1.auth import router as auth_router
    from voter_api.api.v1.boundaries import boundaries_router
    from voter_api.api.v1.datasets import datasets_router
    from voter_api.api.v1.elected_officials import elected_officials_router
    from voter_api.api.v1.elections import elections_router
    from voter_api.api.v1.exports import exports_router
    from voter_api.api.v1.geocoding import geocoding_router
    from voter_api.api.v1.governing_bodies import governing_bodies_router
    from voter_api.api.v1.governing_body_types import governing_body_types_router
    from voter_api.api.v1.imports import router as imports_router
    from voter_api.api.v1.meetings import meetings_router
    from voter_api.api.v1.video_embeds import video_embeds_router
    from voter_api.api.v1.voter_history import voter_history_router
    from voter_api.api.v1.voters import voters_router

    root_router = APIRouter(prefix=settings.api_v1_prefix)
    root_router.include_router(auth_router)
    root_router.include_router(imports_router)
    root_router.include_router(geocoding_router)
    root_router.include_router(voters_router)
    root_router.include_router(boundaries_router)
    root_router.include_router(elected_officials_router)
    root_router.include_router(governing_body_types_router)
    root_router.include_router(governing_bodies_router)
    root_router.include_router(datasets_router)
    root_router.include_router(analysis_router)
    root_router.include_router(exports_router)
    root_router.include_router(elections_router)
    root_router.include_router(voter_history_router)
    root_router.include_router(meetings_router)
    root_router.include_router(agenda_items_router)
    root_router.include_router(attachments_router)
    root_router.include_router(video_embeds_router)

    return root_router


def setup_middleware(app: FastAPI, settings: Settings) -> None:
    """Register all middleware on the FastAPI app.

    Args:
        app: The FastAPI application.
        settings: Application settings.
    """
    setup_cors(app, settings)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
