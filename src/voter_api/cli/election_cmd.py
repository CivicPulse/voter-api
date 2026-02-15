"""CLI commands for election tracking.

Provides manual refresh of election results from GA SoS feeds.
"""

import asyncio
import uuid
from typing import Annotated

import typer
from loguru import logger

election_app = typer.Typer()


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
