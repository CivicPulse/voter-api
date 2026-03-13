"""CLI commands for election tracking.

Provides creation, import, and manual refresh of election results from GA SoS feeds,
plus election calendar preprocessing and import from GA SoS source files.
"""

import asyncio
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

election_app = typer.Typer()


@election_app.command("create")
def create(
    name: Annotated[str, typer.Option("--name", help="Election name")],
    election_date: Annotated[str, typer.Option("--date", help="Election date (YYYY-MM-DD)")],
    election_type: Annotated[
        str,
        typer.Option("--type", help="Election type: special, general, primary, runoff"),
    ],
    district: Annotated[str, typer.Option("--district", help="District name")],
    data_source_url: Annotated[str, typer.Option("--url", help="GA SoS data source URL")],
    refresh_interval: Annotated[int, typer.Option("--refresh-interval", help="Refresh interval in seconds")] = 120,
) -> None:
    """Create a new election and optionally fetch initial results."""
    parsed_date = date.fromisoformat(election_date)
    asyncio.run(_create_impl(name, parsed_date, election_type, district, data_source_url, refresh_interval))


async def _create_impl(
    name: str,
    election_date: date,
    election_type: str,
    district: str,
    data_source_url: str,
    refresh_interval: int,
) -> None:
    """Async implementation of the create command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.schemas.election import ElectionCreateRequest
    from voter_api.services import election_service

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        factory = get_session_factory()
        async with factory() as session:
            request = ElectionCreateRequest(
                name=name,
                election_date=election_date,
                election_type=election_type,
                district=district,
                source="sos_feed",
                data_source_url=data_source_url,
                refresh_interval_seconds=refresh_interval,
            )
            election = await election_service.create_election(session, request)
            typer.echo(f"Created election {election.id}: {election.name} ({election.election_date})")

            try:
                logger.info("Fetching initial results...")
                result = await election_service.refresh_single_election(session, election.id)
                typer.echo(
                    f"Initial refresh: {result.counties_updated} counties, "
                    f"{result.precincts_reporting}/{result.precincts_participating} precincts reporting"
                )
            except Exception as e:
                logger.warning(f"Could not fetch initial results: {e}")
                typer.echo("Election created successfully (initial results fetch skipped)")
    finally:
        await dispose_engine()


@election_app.command("refresh")
def refresh(
    election_id: Annotated[
        str | None,
        typer.Option("--election-id", help="Refresh a specific election by UUID"),
    ] = None,
) -> None:
    """Refresh election results from GA SoS data feeds."""
    asyncio.run(_refresh_impl(election_id))


async def _refresh_impl(election_id_str: str | None) -> None:
    """Async implementation of the refresh command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.services import election_service

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        factory = get_session_factory()
        async with factory() as session:
            if election_id_str:
                eid = uuid.UUID(election_id_str)
                logger.info("Refreshing election {}", eid)
                result = await election_service.refresh_single_election(session, eid)
                typer.echo(
                    f"Refreshed election {result.election_id}: "
                    f"{result.counties_updated} counties updated, "
                    f"{result.precincts_reporting}/{result.precincts_participating} precincts reporting"
                )
            else:
                logger.info("Refreshing all active elections")
                count = await election_service.refresh_all_active_elections(session)
                typer.echo(f"Refreshed {count} active election(s)")
    finally:
        await dispose_engine()


@election_app.command("import-feed")
def import_feed(
    url: Annotated[str, typer.Option("--url", help="GA SoS feed URL")],
    election_type: Annotated[
        str | None,
        typer.Option("--type", help="Election type: special, general, primary, runoff. Auto-detected if omitted."),
    ] = None,
    refresh_interval: Annotated[
        int,
        typer.Option("--refresh-interval", help="Refresh interval in seconds"),
    ] = 120,
    skip_refresh: Annotated[
        bool,
        typer.Option("--skip-refresh", help="Skip initial refresh after import"),
    ] = False,
) -> None:
    """Import all races from an SoS feed as separate elections."""
    asyncio.run(_import_feed_impl(url, election_type, refresh_interval, not skip_refresh))


async def _import_feed_impl(
    url: str,
    election_type: str | None,
    refresh_interval: int,
    auto_refresh: bool,
) -> None:
    """Async implementation of the import-feed command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.lib.election_tracker import FetchError
    from voter_api.schemas.election import FeedImportRequest
    from voter_api.services import election_service

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        factory = get_session_factory()
        async with factory() as session:
            typer.echo(f"Fetching feed from {url}...")

            preview = await election_service.preview_feed_import(url)
            typer.echo(f"\nDiscovered {preview.total_races} race(s):")
            for i, race in enumerate(preview.races, 1):
                typer.echo(f"  {i}. [{race.ballot_item_id}] {race.name} ({race.candidate_count} candidates)")

            if election_type is None:
                typer.echo(f"Detected election type: {preview.detected_election_type}")
            typer.echo("")

            request = FeedImportRequest(
                data_source_url=url,
                election_type=election_type,
                refresh_interval_seconds=refresh_interval,
                auto_refresh=auto_refresh,
            )

            result = await election_service.import_feed(session, request)

            typer.echo(f"Imported {result.elections_created} election(s):")
            for election in result.elections:
                status_label = f" ({election.status})"
                refresh_status = ""
                if election.refreshed:
                    refresh_status = (
                        f" - {election.precincts_reporting}/{election.precincts_participating} precincts reporting"
                    )
                typer.echo(f"  {election.election_id}: {election.name}{status_label}{refresh_status}")
    except FetchError as e:
        typer.echo(f"Error: Failed to fetch feed: {e}", err=True)
        raise typer.Exit(code=1) from e
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    finally:
        await dispose_engine()


@election_app.command("preprocess-calendar")
def preprocess_calendar(
    source_file: Annotated[Path, typer.Argument(help="Source calendar file (XLSX, PDF, or HTML)", exists=True)],
    output: Annotated[Path, typer.Option("--output", help="Output path for JSONL template")],
    merge: Annotated[
        list[Path] | None,
        typer.Option("--merge", help="Additional source files to merge", exists=True),
    ] = None,
) -> None:
    """Preprocess election calendar source(s) into importable JSONL template."""
    from voter_api.lib.election_calendar.preprocessor import preprocess_calendar as _preprocess

    try:
        count = _preprocess(source_file, output, merge_paths=merge)
        typer.echo(f"Wrote {count} calendar entries to {output}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e


@election_app.command("import-calendar")
def import_calendar(
    template: Annotated[Path, typer.Argument(help="Path to calendar JSONL template", exists=True)],
) -> None:
    """Import election calendar dates from a JSONL template."""
    asyncio.run(_import_calendar_impl(template))


async def _import_calendar_impl(template: Path) -> None:
    """Async implementation of the import-calendar command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.lib.election_calendar.parser import parse_calendar_jsonl
    from voter_api.services.election_calendar_service import process_calendar_import

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        try:
            entries = parse_calendar_jsonl(template)
        except Exception as e:
            typer.echo(f"Failed to parse calendar file: {e}")
            raise typer.Exit(code=1) from e

        if not entries:
            typer.echo("No calendar entries found in template.")
            return

        typer.echo(f"Parsed {len(entries)} calendar entries from {template}")

        factory = get_session_factory()
        try:
            async with factory() as session:
                result = await process_calendar_import(session, entries)
        except Exception as e:
            typer.echo(f"Calendar import failed: {e}")
            raise typer.Exit(code=1) from e

        typer.echo("\nCalendar import complete:")
        typer.echo(f"  Matched:   {result.matched}")
        typer.echo(f"  Updated:   {result.updated}")
        typer.echo(f"  Unmatched: {result.unmatched}")
        if result.unmatched_names:
            typer.echo("\nUnmatched elections:")
            for name in result.unmatched_names:
                typer.echo(f"  - {name}")
    finally:
        await dispose_engine()
