"""FastAPI application factory.

Creates the FastAPI app with lifespan management, exception handlers,
and OpenAPI metadata.
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from voter_api import __version__
from voter_api.core.config import get_settings
from voter_api.core.database import dispose_engine, get_session_factory, init_engine
from voter_api.core.logging import setup_logging


async def _recover_stale_analysis_runs() -> None:
    """Mark any 'running' or 'pending' analysis runs as 'failed' on startup.

    In-process background tasks don't survive server restarts, so any runs
    still in these statuses at boot time are orphaned.
    """
    from sqlalchemy import case, func, update

    from voter_api.models.analysis_run import AnalysisRun

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.status.in_(["running", "pending"]))
            .values(
                status="failed",
                notes=case(
                    (
                        AnalysisRun.notes.isnot(None),
                        AnalysisRun.notes + "; Server restarted while task was in progress",
                    ),
                    else_="Server restarted while task was in progress",
                ),
                completed_at=func.now(),
            )
        )
        await session.commit()
        row_count = result.rowcount  # type: ignore[attr-defined]
        if row_count is not None and row_count > 0:
            logger.warning("Recovered {} stale analysis run(s) on startup", row_count)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle: init engine on startup, dispose on shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)
    init_engine(settings.database_url, echo=False, schema=settings.database_schema)

    # Recover analysis runs orphaned by a previous server restart
    await _recover_stale_analysis_runs()

    # Start election auto-refresh background task
    refresh_task = None
    if settings.election_refresh_enabled:
        from voter_api.services.election_service import election_refresh_loop

        refresh_task = asyncio.create_task(election_refresh_loop(settings.election_refresh_interval))

    yield

    # Cancel background refresh task
    if refresh_task is not None:
        refresh_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refresh_task

    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Voter API",
        description="Georgia Secretary of State voter data management with geospatial capabilities",
        version=__version__,
        lifespan=lifespan,
    )

    # Register exception handlers
    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    # Register middleware and routers
    from voter_api.api.router import create_router, setup_middleware

    setup_middleware(app, settings)
    app.include_router(create_router(settings))

    return app
