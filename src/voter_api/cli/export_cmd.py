"""Export CLI commands for bulk voter data export."""

import asyncio
from pathlib import Path

import typer

export_app = typer.Typer()


@export_app.command("run")
def export_run(
    output_format: str = typer.Option("csv", "--format", help="Output format (csv, json, geojson)"),
    county: str | None = typer.Option(None, "--county", help="Filter by county"),
    status_filter: str | None = typer.Option(None, "--status", help="Filter by voter status"),
    match_status: str | None = typer.Option(None, "--match-status", help="Filter by match status"),
    output: Path | None = typer.Option(None, "--output", help="Output directory"),
) -> None:
    """Export voter data to file."""
    asyncio.run(_export_run(output_format, county, status_filter, match_status, output))


async def _export_run(
    output_format: str,
    county: str | None,
    status_filter: str | None,
    match_status: str | None,
    output_dir: Path | None,
) -> None:
    """Async implementation of export."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.export_service import create_export_job, process_export

    settings = get_settings()
    init_engine(settings.database_url)

    export_dir = output_dir or Path(settings.export_dir)

    filters: dict = {}
    if county:
        filters["county"] = county
    if status_filter:
        filters["status"] = status_filter
    if match_status:
        filters["match_status"] = match_status

    try:
        factory = get_session_factory()
        async with factory() as session:
            job = await create_export_job(
                session,
                output_format=output_format,
                filters=filters,
            )
            typer.echo(f"Export job created: {job.id}")
            typer.echo(f"Format: {output_format}")
            typer.echo("Processing...")

            job = await process_export(session, job, export_dir)

            typer.echo(f"\nExport {'completed' if job.status == 'completed' else 'failed'}:")
            typer.echo(f"  Records:    {job.record_count or 0}")
            typer.echo(f"  File size:  {job.file_size_bytes or 0} bytes")
            typer.echo(f"  File path:  {job.file_path or 'N/A'}")
    finally:
        await dispose_engine()
