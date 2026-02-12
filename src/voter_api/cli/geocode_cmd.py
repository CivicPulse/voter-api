"""Geocoding CLI commands for batch geocoding and manual coordinate entry."""

import asyncio
import uuid

import typer

geocode_app = typer.Typer()


@geocode_app.command("batch")
def batch_geocode(
    county: str | None = typer.Option(None, "--county", help="Limit to specific county"),
    provider: str = typer.Option("census", "--provider", help="Geocoder provider"),
    force: bool = typer.Option(False, "--force", help="Re-geocode already geocoded records"),  # noqa: FBT001
    batch_size: int = typer.Option(100, "--batch-size", help="Records per batch"),  # noqa: B008
) -> None:
    """Run batch geocoding for voter addresses."""
    asyncio.run(_batch_geocode(county, provider, force, batch_size))


@geocode_app.command("manual")
def manual_geocode(
    voter_id: str = typer.Argument(..., help="Voter UUID"),  # noqa: B008
    lat: float = typer.Option(..., "--lat", help="Latitude (-90 to 90)"),  # noqa: B008
    lon: float = typer.Option(..., "--lon", help="Longitude (-180 to 180)"),  # noqa: B008
) -> None:
    """Manually set coordinates for a voter."""
    asyncio.run(_manual_geocode(voter_id, lat, lon))


async def _batch_geocode(county: str | None, provider: str, force: bool, batch_size: int) -> None:
    """Async implementation of batch geocoding."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.geocoding_service import create_geocoding_job, process_geocoding_job

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            job = await create_geocoding_job(
                session,
                provider=provider,
                county=county,
                force_regeocode=force,
            )
            typer.echo(f"Geocoding job created: {job.id}")
            typer.echo(f"Provider: {provider}, County: {county or 'all'}")

            job = await process_geocoding_job(session, job, batch_size=batch_size)

            typer.echo(f"\nGeocoding {'completed' if job.status == 'completed' else 'failed'}:")
            typer.echo(f"  Total records:  {job.total_records or 0}")
            typer.echo(f"  Processed:      {job.processed or 0}")
            typer.echo(f"  Succeeded:      {job.succeeded or 0}")
            typer.echo(f"  Failed:         {job.failed or 0}")
            typer.echo(f"  Cache hits:     {job.cache_hits or 0}")
    finally:
        await dispose_engine()


async def _manual_geocode(voter_id_str: str, lat: float, lon: float) -> None:
    """Async implementation of manual geocoding."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.services.geocoding_service import add_manual_location

    settings = get_settings()
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            vid = uuid.UUID(voter_id_str)
            location = await add_manual_location(
                session, voter_id=vid, latitude=lat, longitude=lon, set_as_primary=True
            )
            typer.echo(f"Manual location added: {location.id}")
            typer.echo(f"  Voter: {vid}")
            typer.echo(f"  Lat/Lon: {lat}, {lon}")
            typer.echo(f"  Primary: {location.is_primary}")
    finally:
        await dispose_engine()
