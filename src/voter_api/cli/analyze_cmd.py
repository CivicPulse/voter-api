"""Analysis CLI commands for triggering and checking location analysis."""

import asyncio
import csv
import json
import sys
import uuid
from pathlib import Path
from typing import TextIO

import typer

from voter_api.models.analysis_result import AnalysisResult

analyze_app = typer.Typer()


@analyze_app.command("run")
def analyze_run(
    county: str | None = typer.Option(None, "--county", help="Limit analysis to a county"),
    notes: str | None = typer.Option(None, "--notes", help="Notes for this analysis run"),
    batch_size: int = typer.Option(100, "--batch-size", help="Voters per batch"),
) -> None:
    """Run location analysis comparing voter registrations to geocoded locations."""
    asyncio.run(_analyze_run(county, notes, batch_size))


@analyze_app.command("export-mismatches")
def export_mismatches(
    output_format: str = typer.Option("csv", "--format", help="Output format (csv, json)"),
    county: str | None = typer.Option(None, "--county", help="Filter by county"),
    output: Path | None = typer.Option(None, "--output", help="Output file (default: stdout)"),
    run_id: str | None = typer.Option(None, "--run-id", help="Specific analysis run ID (default: latest completed)"),
) -> None:
    """Export voters with district mismatches to CSV or JSON."""
    valid_formats = ("csv", "json")
    if output_format not in valid_formats:
        typer.echo(f"Invalid format '{output_format}'. Must be one of: {', '.join(valid_formats)}", err=True)
        raise typer.Exit(code=1)
    try:
        parsed_run_id = uuid.UUID(run_id) if run_id else None
    except ValueError:
        typer.echo(f"Invalid run ID: '{run_id}' is not a valid UUID.", err=True)
        raise typer.Exit(code=1)  # noqa: B904
    asyncio.run(_export_mismatches(output_format, county, output, parsed_run_id))


async def _export_mismatches(
    output_format: str,
    county: str | None,
    output_path: Path | None,
    run_id: uuid.UUID | None,
) -> None:
    """Async implementation of export-mismatches."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.models.analysis_run import AnalysisRun
    from voter_api.models.voter import Voter

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            # Resolve the target run
            if run_id:
                run_result = await session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))
                run = run_result.scalar_one_or_none()
                if not run:
                    typer.echo(f"Analysis run {run_id} not found.", err=True)
                    raise typer.Exit(code=1)
            else:
                run_result = await session.execute(
                    select(AnalysisRun)
                    .where(AnalysisRun.status == "completed")
                    .order_by(AnalysisRun.completed_at.desc())
                    .limit(1)
                )
                run = run_result.scalar_one_or_none()
                if not run:
                    typer.echo("No completed analysis runs found.", err=True)
                    raise typer.Exit(code=1)

            typer.echo(f"Using analysis run: {run.id} (completed {run.completed_at})", err=True)

            # Query mismatched results with voter data (exclude match,
            # unable-to-analyze, and not-geocoded — only true mismatches)
            mismatch_statuses = ("mismatch-district", "mismatch-precinct", "mismatch-both")
            query = (
                select(AnalysisResult)
                .options(selectinload(AnalysisResult.voter))
                .where(AnalysisResult.analysis_run_id == run.id)
                .where(AnalysisResult.match_status.in_(mismatch_statuses))
            )

            if county:
                query = query.join(Voter, AnalysisResult.voter_id == Voter.id).where(Voter.county == county)

            query = query.order_by(AnalysisResult.analyzed_at)
            result = await session.execute(query)
            results = list(result.scalars().all())

            typer.echo(f"Found {len(results)} mismatched voters.", err=True)

            # Write output
            out = output_path.open("w", newline="") if output_path else sys.stdout
            try:
                if output_format == "json":
                    _write_json(out, results)
                else:
                    _write_csv(out, results)
            finally:
                if output_path:
                    out.close()

            if output_path:
                typer.echo(f"Written to {output_path}", err=True)
    finally:
        await dispose_engine()


def _write_csv(out: TextIO, results: list[AnalysisResult]) -> None:
    """Write mismatch results as CSV."""
    writer = csv.writer(out)
    writer.writerow(
        [
            "voter_registration_number",
            "first_name",
            "last_name",
            "county",
            "match_status",
            "mismatch_details",
        ]
    )
    for ar in results:
        voter = ar.voter
        details = ""
        if ar.mismatch_details:
            parts = []
            for d in ar.mismatch_details:
                parts.append(f"{d.get('boundary_type', '?')}: {d.get('registered', '?')}->{d.get('determined', '?')}")
            details = "; ".join(parts)
        writer.writerow(
            [
                voter.voter_registration_number if voter else "",
                voter.first_name if voter else "",
                voter.last_name if voter else "",
                voter.county if voter else "",
                ar.match_status,
                details,
            ]
        )


def _write_json(out: TextIO, results: list[AnalysisResult]) -> None:
    """Write mismatch results as JSON."""
    items = []
    for ar in results:
        voter = ar.voter
        items.append(
            {
                "voter_registration_number": voter.voter_registration_number if voter else None,
                "first_name": voter.first_name if voter else None,
                "last_name": voter.last_name if voter else None,
                "county": voter.county if voter else None,
                "match_status": ar.match_status,
                "mismatch_details": ar.mismatch_details,
                "determined_boundaries": ar.determined_boundaries,
                "registered_boundaries": ar.registered_boundaries,
            }
        )
    json.dump(items, out, indent=2, default=str)
    out.write("\n")


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
