"""Analysis CLI commands for triggering and checking location analysis."""

import asyncio

import typer

analyze_app = typer.Typer()


@analyze_app.command("run")
def analyze_run(
    county: str | None = typer.Option(None, "--county", help="Limit analysis to a county"),
    notes: str | None = typer.Option(None, "--notes", help="Notes for this analysis run"),
    batch_size: int = typer.Option(100, "--batch-size", help="Voters per batch"),
) -> None:
    """Run location analysis comparing voter registrations to geocoded locations."""
    asyncio.run(_analyze_run(county, notes, batch_size))


async def _analyze_run(county: str | None, notes: str | None, batch_size: int) -> None:
    """Async implementation of analysis run."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.analysis_service import create_analysis_run, process_analysis_run

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            run = await create_analysis_run(session, notes=notes)
            typer.echo(f"Analysis run created: {run.id}")
            typer.echo("Processing...")

            run = await process_analysis_run(session, run, county=county, batch_size=batch_size)

            typer.echo(f"\nAnalysis {'completed' if run.status == 'completed' else 'failed'}:")
            typer.echo(f"  Total analyzed:     {run.total_voters_analyzed or 0}")
            typer.echo(f"  Matches:            {run.match_count or 0}")
            typer.echo(f"  Mismatches:         {run.mismatch_count or 0}")
            typer.echo(f"  Unable to analyze:  {run.unable_to_analyze_count or 0}")
    finally:
        await dispose_engine()
