"""CLI commands for markdown normalization.

Provides the ``voter-api normalize`` command group with ``elections``
and ``candidates`` subcommands. Applies normalization rules (title case,
date formatting, URL normalization, occupation formatting) to markdown
files in a directory.

Each command optionally creates an ``ImportJob`` DB record
(file_type='normalize') when DATABASE_URL is available.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003

import typer
from loguru import logger

from voter_api.lib.normalizer import normalize_directory

normalize_app = typer.Typer()


# ---------------------------------------------------------------------------
# DB integration helpers
# ---------------------------------------------------------------------------


async def _create_normalize_job(directory_name: str) -> str | None:
    """Create an ImportJob DB record for a normalize run.

    Args:
        directory_name: Name of the directory being normalized (for file_name).

    Returns:
        Job ID string if created successfully, or None if DB is unavailable.
    """
    try:
        from voter_api.core.config import get_settings
        from voter_api.core.database import get_session_factory, init_engine
        from voter_api.models.import_job import ImportJob

        settings = get_settings()
        init_engine(settings.database_url, schema=settings.database_schema)

        factory = get_session_factory()
        async with factory() as session:
            job = ImportJob(
                file_name=directory_name,
                file_type="normalize",
                status="processing",
                started_at=datetime.now(UTC),
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return str(job.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"DB unavailable, skipping job tracking: {exc}")
        return None


async def _complete_normalize_job(
    job_id: str,
    *,
    files_processed: int,
    files_succeeded: int,
    files_failed: int,
    error_details: list[dict[str, str]] | None = None,
) -> None:
    """Update an ImportJob record after normalization completes.

    Args:
        job_id: The UUID string of the job to update.
        files_processed: Total files processed.
        files_succeeded: Files that normalized successfully.
        files_failed: Files that failed normalization.
        error_details: Optional list of error detail dicts for JSONB error_log.
    """
    try:
        import uuid

        from sqlalchemy import select

        from voter_api.core.database import get_session_factory
        from voter_api.models.import_job import ImportJob

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(select(ImportJob).where(ImportJob.id == uuid.UUID(job_id)))
            job = result.scalar_one_or_none()
            if job is not None:
                job.status = "completed" if files_failed == 0 else "failed"
                job.total_records = files_processed
                job.records_succeeded = files_succeeded
                job.records_failed = files_failed
                job.completed_at = datetime.now(UTC)
                if error_details:
                    job.error_log = error_details
                await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"DB unavailable, skipping job completion update: {exc}")


async def _dispose_db() -> None:
    """Dispose the database engine if it was initialized."""
    try:
        from voter_api.core.database import dispose_engine

        await dispose_engine()
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Engine disposal skipped: {exc}")


# ---------------------------------------------------------------------------
# elections subcommand
# ---------------------------------------------------------------------------


@normalize_app.command("elections")
def normalize_elections(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to election directory to normalize.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False,
        "--dry-run",
        help="Report changes without writing to disk.",
    ),
    report: Path | None = typer.Option(  # noqa: B008
        None,
        "--report",
        help="Write JSON report to this file path.",
    ),
) -> None:
    """Normalize markdown election files in a directory.

    Applies title case to name fields, normalizes dates and URLs,
    formats occupation strings, and flags ALL CAPS remnants. Processes
    overview, single-contest, and multi-contest markdown files.
    """
    # Create DB job record (graceful degradation if DB unavailable)
    job_id = asyncio.run(_create_normalize_job(directory.name))

    norm_report = normalize_directory(
        directory,
        dry_run=dry_run,
        report_path=report,
    )

    # Build error details for DB logging
    error_log: list[dict[str, str]] | None = None
    if norm_report.files_failed > 0:
        error_log = [{"message": f"File normalization failures: {norm_report.files_failed}"}]

    if job_id:
        asyncio.run(
            _complete_normalize_job(
                job_id,
                files_processed=norm_report.files_processed,
                files_succeeded=norm_report.files_succeeded,
                files_failed=norm_report.files_failed,
                error_details=error_log,
            )
        )
        asyncio.run(_dispose_db())

    # Print terminal report
    typer.echo(norm_report.render_terminal())

    if norm_report.files_failed > 0:
        typer.echo(
            f"{norm_report.files_failed} file(s) failed normalization.",
            err=True,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# candidates subcommand
# ---------------------------------------------------------------------------


@normalize_app.command("candidates")
def normalize_candidates(
    directory: Path = typer.Argument(  # noqa: B008
        ...,
        help="Path to candidates directory to normalize.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    dry_run: bool = typer.Option(  # noqa: B008
        False,
        "--dry-run",
        help="Report changes without writing to disk.",
    ),
    report: Path | None = typer.Option(  # noqa: B008
        None,
        "--report",
        help="Write JSON report to this file path.",
    ),
) -> None:
    """Normalize candidate markdown files in a directory.

    Applies title case to names, normalizes URLs and dates, formats
    occupations, and generates UUIDs for candidates missing IDs.
    Renames placeholder filenames (00000000) to use UUID prefix.
    """
    from voter_api.lib.normalizer import detect_file_type
    from voter_api.lib.normalizer.uuid_handler import ensure_uuid, rename_candidate_file

    # Create DB job record
    job_id = asyncio.run(_create_normalize_job(directory.name))

    norm_report = normalize_directory(
        directory,
        dry_run=dry_run,
        report_path=report,
        file_type="candidate",
    )

    # UUID generation and file renaming for candidate files
    if not dry_run:
        candidate_files = sorted(directory.rglob("*.md"))
        candidate_files = [f for f in candidate_files if f.name != "README.md" and detect_file_type(f) == "candidate"]
        for file_path in candidate_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                new_content, generated_uuid = ensure_uuid(content)
                if generated_uuid:
                    file_path.write_text(new_content, encoding="utf-8")
                    norm_report.add_uuid_generated(file_path)
                    new_path = rename_candidate_file(file_path, generated_uuid)
                    if new_path:
                        norm_report.add_file_renamed(file_path, new_path)
            except ValueError as exc:
                logger.warning(f"UUID error for {file_path}: {exc}")
            except OSError as exc:
                logger.warning(f"File error for {file_path}: {exc}")

    # Build error details for DB logging
    error_log = None
    if norm_report.files_failed > 0:
        error_log = [{"message": f"File normalization failures: {norm_report.files_failed}"}]

    if job_id:
        asyncio.run(
            _complete_normalize_job(
                job_id,
                files_processed=norm_report.files_processed,
                files_succeeded=norm_report.files_succeeded,
                files_failed=norm_report.files_failed,
                error_details=error_log,
            )
        )
        asyncio.run(_dispose_db())

    # Print terminal report
    typer.echo(norm_report.render_terminal())

    if norm_report.files_failed > 0:
        typer.echo(
            f"{norm_report.files_failed} file(s) failed normalization.",
            err=True,
        )
        sys.exit(1)
