"""Import CLI commands for voter files and boundary files."""

import asyncio
from pathlib import Path

import typer

import_app = typer.Typer()


@import_app.command("voters")
def import_voters(
    file: Path = typer.Argument(..., help="Path to voter CSV file", exists=True),  # noqa: B008
    batch_size: int = typer.Option(1000, "--batch-size", help="Records per batch"),  # noqa: B008
) -> None:
    """Import voter data from a CSV file."""
    asyncio.run(_import_voters(file, batch_size))


async def _import_voters(file_path: Path, batch_size: int) -> None:
    """Async implementation of voter import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.import_service import create_import_job, process_voter_import

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            job = await create_import_job(session, file_name=file_path.name)
            typer.echo(f"Import job created: {job.id}")
            typer.echo(f"Processing {file_path}...")

            job = await process_voter_import(session, job, file_path, batch_size)

            typer.echo(f"\nImport {'completed' if job.status == 'completed' else 'failed'}:")
            typer.echo(f"  Total records:  {job.total_records or 0}")
            typer.echo(f"  Succeeded:      {job.records_succeeded or 0}")
            typer.echo(f"  Failed:         {job.records_failed or 0}")
            typer.echo(f"  Inserted:       {job.records_inserted or 0}")
            typer.echo(f"  Updated:        {job.records_updated or 0}")
            typer.echo(f"  Soft-deleted:   {job.records_soft_deleted or 0}")
    finally:
        await dispose_engine()


@import_app.command("boundaries")
def import_boundaries_cmd(
    file: Path = typer.Argument(..., help="Path to shapefile or GeoJSON", exists=True),
    boundary_type: str = typer.Option(..., "--type", help="Boundary type (e.g., congressional)"),
    source: str = typer.Option(..., "--source", help="Data source (state or county)"),
    county: str | None = typer.Option(None, "--county", help="County name"),
) -> None:
    """Import boundary data from a shapefile or GeoJSON file."""
    asyncio.run(_import_boundaries(file, boundary_type, source, county))


async def _import_boundaries(file_path: Path, boundary_type: str, source: str, county: str | None) -> None:
    """Async implementation of boundary import."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.boundary_service import import_boundaries

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            boundaries = await import_boundaries(
                session,
                file_path=file_path,
                boundary_type=boundary_type,
                source=source,
                county=county,
            )
            typer.echo(f"Imported {len(boundaries)} boundaries")
            typer.echo(f"  Type:   {boundary_type}")
            typer.echo(f"  Source: {source}")
            typer.echo(f"  County: {county or 'all'}")
    finally:
        await dispose_engine()
