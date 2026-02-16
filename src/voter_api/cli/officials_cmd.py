"""CLI commands for elected officials data loading.

Provides fetch (single district) and sync (all districts) commands
for loading elected official data from external providers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

import typer
from loguru import logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from voter_api.core.config import Settings
    from voter_api.lib.officials.base import BaseOfficialsProvider

officials_app = typer.Typer()


@officials_app.command("fetch")
def fetch(
    provider: Annotated[str, typer.Option("--provider", help="Provider name (open_states or congress_gov)")],
    boundary_type: Annotated[
        str, typer.Option("--type", help="Boundary type (state_senate, state_house, congressional, us_senate)")
    ],
    district: Annotated[str, typer.Option("--district", help="District identifier (number or GA for senate)")],
) -> None:
    """Fetch officials for a single district from a specific provider."""
    asyncio.run(_fetch_impl(provider, boundary_type, district))


async def _fetch_impl(provider_name: str, boundary_type: str, district: str) -> None:
    """Async implementation of the fetch command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.services import elected_official_service

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    provider: BaseOfficialsProvider | None = None
    try:
        provider = _create_provider(provider_name, settings)
        records = await provider.fetch_by_district(boundary_type, district)
        logger.info("Fetched {} records from {}", len(records), provider_name)

        factory = get_session_factory()
        async with factory() as session:
            sources = await elected_official_service.upsert_source_records(session, records)
            created = await elected_official_service.auto_create_officials_from_sources(
                session, boundary_type, district
            )

        typer.echo(
            f"Provider: {provider_name} | District: {boundary_type}/{district}\n"
            f"  Records fetched: {len(records)}\n"
            f"  Sources upserted: {len(sources)}\n"
            f"  Officials auto-created: {len(created)}"
        )
    finally:
        if provider is not None:
            await provider.close()
        await dispose_engine()


@officials_app.command("sync")
def sync(
    provider: Annotated[
        str, typer.Option("--provider", help="Provider to sync (open_states, congress_gov, or all)")
    ] = "all",
) -> None:
    """Sync all Georgia officials for a provider (or all providers)."""
    asyncio.run(_sync_impl(provider))


async def _sync_impl(provider_name: str) -> None:
    """Async implementation of the sync command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        if provider_name not in ("open_states", "congress_gov", "all"):
            typer.echo(f"Unknown provider: {provider_name}. Use open_states, congress_gov, or all.")
            raise typer.Exit(code=1)

        factory = get_session_factory()
        had_error = False

        if provider_name in ("open_states", "all"):
            if settings.open_states_api_key:
                try:
                    await _sync_open_states(settings, factory)
                except Exception:
                    logger.exception("Open States sync failed")
                    typer.echo("Error: Open States sync failed (see logs for details)")
                    had_error = True
            else:
                typer.echo("Skipping Open States: OPEN_STATES_API_KEY not configured")

        if provider_name in ("congress_gov", "all"):
            if settings.congress_gov_api_key:
                try:
                    await _sync_congress_gov(settings, factory)
                except Exception:
                    logger.exception("Congress.gov sync failed")
                    typer.echo("Error: Congress.gov sync failed (see logs for details)")
                    had_error = True
            else:
                typer.echo("Skipping Congress.gov: CONGRESS_GOV_API_KEY not configured")

        if had_error:
            raise typer.Exit(code=1)
    finally:
        await dispose_engine()


async def _sync_open_states(settings: Settings, factory: async_sessionmaker[AsyncSession]) -> None:
    """Sync all GA state legislators from Open States."""
    from voter_api.lib.officials.open_states import OpenStatesProvider
    from voter_api.services import elected_official_service

    if not settings.open_states_api_key:
        raise typer.BadParameter("OPEN_STATES_API_KEY is required for Open States sync")
    provider = OpenStatesProvider(api_key=settings.open_states_api_key)
    total_records = 0
    total_sources = 0
    total_created = 0

    try:
        for chamber, label in [("upper", "State Senate"), ("lower", "State House")]:
            typer.echo(f"Fetching {label} members from Open States...")
            records = await provider.fetch_all_for_chamber(chamber)
            total_records += len(records)
            logger.info("Fetched {} {} members", len(records), label)

            async with factory() as session:
                sources = await elected_official_service.upsert_source_records(session, records)
                total_sources += len(sources)

                # Auto-create officials for each unique district
                districts = {(r.boundary_type, r.district_identifier) for r in records}
                for bt, di in sorted(districts):
                    created = await elected_official_service.auto_create_officials_from_sources(session, bt, di)
                    total_created += len(created)

        typer.echo(
            f"\nOpen States sync complete:\n"
            f"  Records fetched: {total_records}\n"
            f"  Sources upserted: {total_sources}\n"
            f"  Officials auto-created: {total_created}"
        )
    finally:
        await provider.close()


async def _sync_congress_gov(settings: Settings, factory: async_sessionmaker[AsyncSession]) -> None:
    """Sync all GA federal members from Congress.gov."""
    from voter_api.lib.officials.congress_gov import CongressGovProvider
    from voter_api.services import elected_official_service

    if not settings.congress_gov_api_key:
        raise typer.BadParameter("CONGRESS_GOV_API_KEY is required for Congress.gov sync")
    provider = CongressGovProvider(api_key=settings.congress_gov_api_key)

    try:
        typer.echo("Fetching GA members from Congress.gov...")
        records = await provider.fetch_all_ga_members()
        logger.info("Fetched {} GA federal members", len(records))

        total_sources = 0
        total_created = 0

        async with factory() as session:
            sources = await elected_official_service.upsert_source_records(session, records)
            total_sources = len(sources)

            # Auto-create officials for each unique district
            districts = {(r.boundary_type, r.district_identifier) for r in records}
            for bt, di in sorted(districts):
                created = await elected_official_service.auto_create_officials_from_sources(session, bt, di)
                total_created += len(created)

        typer.echo(
            f"\nCongress.gov sync complete:\n"
            f"  Records fetched: {len(records)}\n"
            f"  Sources upserted: {total_sources}\n"
            f"  Officials auto-created: {total_created}"
        )
    finally:
        await provider.close()


def _create_provider(provider_name: str, settings: Settings) -> BaseOfficialsProvider:
    """Create a provider instance with the appropriate API key.

    Args:
        provider_name: Provider name.
        settings: Application settings.

    Returns:
        Provider instance.
    """
    from voter_api.lib.officials import get_provider

    if provider_name == "open_states":
        if not settings.open_states_api_key:
            typer.echo("Error: OPEN_STATES_API_KEY not configured")
            raise typer.Exit(code=1)
        return get_provider(provider_name, api_key=settings.open_states_api_key)
    if provider_name == "congress_gov":
        if not settings.congress_gov_api_key:
            typer.echo("Error: CONGRESS_GOV_API_KEY not configured")
            raise typer.Exit(code=1)
        return get_provider(provider_name, api_key=settings.congress_gov_api_key)
    typer.echo(f"Unknown provider: {provider_name}")
    raise typer.Exit(code=1)
