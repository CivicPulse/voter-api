"""Voter history CLI commands for the import command group."""

import asyncio
import time
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
    from voter_api.services.election_resolution_service import resolve_voter_history_elections
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

            start = time.monotonic()
            job = await process_voter_history_import(session, job, file_path, batch_size)
            elapsed = time.monotonic() - start

            status_label = "completed" if job.status == "completed" else "failed"
            typer.echo(f"\nImport {status_label} in {elapsed:.1f}s:")
            typer.echo(f"  Total records:     {job.total_records or 0}")
            typer.echo(f"  Succeeded:         {job.records_succeeded or 0}")
            typer.echo(f"  Failed:            {job.records_failed or 0}")
            typer.echo(f"  Skipped (dupes):   {job.records_skipped or 0}")
            typer.echo(f"  Unmatched voters:  {job.records_unmatched or 0}")

            if job.status == "completed":
                typer.echo("\nResolving voter history to elections...")
                resolve_start = time.monotonic()
                resolution = await resolve_voter_history_elections(session)
                resolve_elapsed = time.monotonic() - resolve_start

                typer.echo(f"Resolution completed in {resolve_elapsed:.1f}s:")
                typer.echo(f"  Linked (tier 0):   {resolution.tier0_updated}")
                typer.echo(f"  Linked (tier 1):   {resolution.tier1_updated}")
                typer.echo(f"  Linked (tier 2):   {resolution.tier2_updated}")
                typer.echo(f"  Unresolvable:      {resolution.unresolvable}")
                if resolution.elections_backfilled:
                    typer.echo(f"  Elections parsed:  {resolution.elections_backfilled}")
    finally:
        await dispose_engine()
