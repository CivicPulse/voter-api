"""Voter history CLI commands for the import command group."""

import asyncio
from pathlib import Path

import typer


def import_voter_history(
    file: Path = typer.Argument(..., help="Path to voter history CSV file", exists=True),  # noqa: B008
    batch_size: int = typer.Option(1000, "--batch-size", help="Records per batch"),  # noqa: B008
) -> None:
    """Import voter participation history from a GA SoS CSV file."""
    asyncio.run(_import_voter_history(file, batch_size))


async def _import_voter_history(file_path: Path, batch_size: int) -> None:
    """Async implementation of voter history import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.import_service import create_import_job
    from voter_api.services.voter_history_service import process_voter_history_import

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            job = await create_import_job(session, file_name=file_path.name, file_type="voter_history")
            typer.echo(f"Import job created: {job.id}")
            typer.echo(f"Importing voter history from {file_path.name}...")

            job = await process_voter_history_import(session, job, file_path, batch_size)

            status_label = "completed" if job.status == "completed" else "failed"
            typer.echo(f"\nImport {status_label}:")
            typer.echo(f"  Total records:     {job.total_records or 0}")
            typer.echo(f"  Succeeded:         {job.records_succeeded or 0}")
            typer.echo(f"  Failed:            {job.records_failed or 0}")
            typer.echo(f"  Skipped (dupes):   {job.records_skipped or 0}")
            typer.echo(f"  Unmatched voters:  {job.records_unmatched or 0}")
    finally:
        await dispose_engine()
