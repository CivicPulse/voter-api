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


async def _recover_stale_geocoding_jobs() -> None:
    """Mark any 'running' or 'pending' geocoding jobs as 'failed' on startup.

    In-process background tasks don't survive server restarts, so any jobs
    still in these statuses at boot time are orphaned. Appends a recovery
    note to the JSONB error_log array.
    """
    from sqlalchemy import func, type_coerce, update
    from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE

    from voter_api.models.geocoding_job import GeocodingJob

    recovery_note = [{"error": "Server restarted while task was in progress"}]

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            update(GeocodingJob)
            .where(GeocodingJob.status.in_(["running", "pending"]))
            .values(
                status="failed",
                error_log=func.coalesce(GeocodingJob.error_log, type_coerce([], JSONB_TYPE))
                + type_coerce(recovery_note, JSONB_TYPE),
                completed_at=func.now(),
            )
        )
        await session.commit()
        row_count = result.rowcount  # type: ignore[attr-defined]
        if row_count is not None and row_count > 0:
            logger.warning("Recovered {} stale geocoding job(s) on startup", row_count)


async def _verify_import_db_state() -> None:
    """Check and repair database state that may be inconsistent after a bulk import crash.

    Specifically checks for:
    1. Autovacuum disabled on the voters table (left disabled if import crashed mid-way)
    2. Missing indexes that were dropped for bulk import but never rebuilt
    """
    from sqlalchemy import text as sa_text

    from voter_api.services.import_service import _DROPPABLE_INDEXES

    factory = get_session_factory()
    async with factory() as session:
        # Check if autovacuum is disabled on voters table
        result = await session.execute(sa_text("SELECT reloptions FROM pg_class WHERE relname = 'voters'"))
        row = result.first()
        if row and row[0] and "autovacuum_enabled=false" in str(row[0]):
            logger.warning("Autovacuum is disabled on voters table — re-enabling after crash recovery")
            await session.execute(sa_text("ALTER TABLE voters SET (autovacuum_enabled = true)"))
            await session.commit()

        # Check for missing indexes and rebuild them
        for idx in _DROPPABLE_INDEXES:
            result = await session.execute(
                sa_text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
                {"name": idx["name"]},
            )
            if result.first() is None:
                logger.warning("Missing index {} — rebuilding after crash recovery", idx["name"])
                await session.execute(sa_text(idx["create"]))
                await session.commit()


async def _recover_stale_import_jobs() -> None:
    """Mark any 'running' or 'pending' import jobs as 'failed' on startup.

    In-process background tasks don't survive server restarts, so any jobs
    still in these statuses at boot time are orphaned. Appends a recovery
    note to the JSONB error_log array.
    """
    from sqlalchemy import func, type_coerce, update
    from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE

    from voter_api.models.import_job import ImportJob

    recovery_note = [{"error": "Server restarted while task was in progress"}]

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            update(ImportJob)
            .where(ImportJob.status.in_(["running", "pending"]))
            .values(
                status="failed",
                error_log=func.coalesce(ImportJob.error_log, type_coerce([], JSONB_TYPE))
                + type_coerce(recovery_note, JSONB_TYPE),
                completed_at=func.now(),
            )
        )
        await session.commit()
        row_count = result.rowcount  # type: ignore[attr-defined]
        if row_count is not None and row_count > 0:
            logger.warning("Recovered {} stale import job(s) on startup", row_count)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle: init engine on startup, dispose on shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level, log_dir=settings.log_dir)
    init_engine(settings.database_url, echo=False, schema=settings.database_schema)

    # Recover analysis runs orphaned by a previous server restart
    try:
        await _recover_stale_analysis_runs()
    except Exception:
        logger.warning("Could not recover stale analysis runs on startup (table may not exist yet)")

    # Recover geocoding jobs orphaned by a previous server restart
    try:
        await _recover_stale_geocoding_jobs()
    except Exception:
        logger.warning("Could not recover stale geocoding jobs on startup (table may not exist yet)")

    # Verify DB state consistency after potential bulk import crash
    try:
        await _verify_import_db_state()
    except Exception:
        logger.warning("Could not verify import DB state on startup (table may not exist yet)")

    # Recover import jobs orphaned by a previous server restart
    try:
        await _recover_stale_import_jobs()
    except Exception:
        logger.warning("Could not recover stale import jobs on startup (table may not exist yet)")

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
