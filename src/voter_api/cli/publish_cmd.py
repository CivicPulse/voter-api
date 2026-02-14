"""Publish CLI commands for static dataset publishing to object storage."""

import asyncio
from importlib.metadata import version
from typing import Any

import typer
from loguru import logger

publish_app = typer.Typer(name="publish", help="Publish static datasets to object storage.")


def _get_publisher_version() -> str:
    """Get the project version for the manifest publisher_version field."""
    try:
        return version("voter-api")
    except Exception:
        return "unknown"


def _create_r2_client_from_settings(settings: Any) -> Any:
    """Create an R2 client from application settings.

    Args:
        settings: Application settings with R2 configuration.

    Returns:
        Configured boto3 S3 client.

    Raises:
        typer.Exit: If R2 is not configured.
    """
    from voter_api.lib.publisher.storage import create_r2_client

    if not settings.r2_enabled:
        typer.echo("Error: R2 publishing is not configured. Set R2_ENABLED=true.")
        raise typer.Exit(code=1)

    if not all([settings.r2_account_id, settings.r2_access_key_id, settings.r2_secret_access_key, settings.r2_bucket]):
        typer.echo(
            "Error: Missing required R2 configuration. Check R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, and R2_BUCKET."
        )
        raise typer.Exit(code=1)

    return create_r2_client(
        account_id=settings.r2_account_id,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=settings.r2_secret_access_key,
    )


@publish_app.command("datasets")
def datasets_command(
    boundary_type: str | None = typer.Option(None, "--boundary-type", help="Publish only this boundary type"),
    county: str | None = typer.Option(None, "--county", help="Republish types containing this county's boundaries"),
    source: str | None = typer.Option(None, "--source", help="Republish types containing this source's boundaries"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed progress"),
) -> None:
    """Generate and upload boundary GeoJSON datasets to R2."""
    asyncio.run(_datasets_command(boundary_type=boundary_type, county=county, source=source, verbose=verbose))


async def _datasets_command(
    *,
    boundary_type: str | None = None,
    county: str | None = None,
    source: str | None = None,
    verbose: bool = False,
) -> None:
    """Async implementation of the datasets publish command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.lib.publisher.storage import validate_config
    from voter_api.services.publish_service import publish_datasets

    settings = get_settings()
    client = _create_r2_client_from_settings(settings)

    # Narrow type — _create_r2_client_from_settings already validates these are set
    assert settings.r2_bucket is not None

    # Validate bucket access before doing any work
    try:
        validate_config(client, settings.r2_bucket)
    except Exception as exc:
        typer.echo(f"Error: Failed to connect to R2: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo("Connected to R2 — starting publish...")
    init_engine(settings.database_url)

    try:
        factory = get_session_factory()
        async with factory() as session:
            result = await publish_datasets(
                session,
                client,
                settings.r2_bucket,
                settings.r2_public_url or "",
                settings.r2_prefix,
                publisher_version=_get_publisher_version(),
                boundary_type=boundary_type,
                county=county,
                source=source,
            )

        if not result.datasets:
            typer.echo("No boundaries found in the database — no datasets published.")
            return

        typer.echo(f"\nPublished {len(result.datasets)} datasets:")
        for ds in result.datasets:
            size_mb = ds.file_size_bytes / (1024 * 1024)
            typer.echo(f"  {ds.name:30s}  {ds.record_count:>6,} features  {size_mb:>7.1f} MB")
            if verbose:
                typer.echo(f"    URL: {ds.public_url}")

        total_mb = result.total_size_bytes / (1024 * 1024)
        typer.echo(f"\nTotal: {result.total_records:,} records, {total_mb:.1f} MB")
        typer.echo(f"Duration: {result.duration_seconds:.1f}s")
        typer.echo(f"Manifest: {result.manifest_key}")

    except Exception as exc:
        logger.error("Publish failed: {}", exc)
        typer.echo(f"Error: Publish failed — {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        await dispose_engine()


@publish_app.command("status")
def status_command() -> None:
    """Show status of published datasets on R2."""
    asyncio.run(_status_command())


async def _status_command() -> None:
    """Async implementation of the status command."""
    from voter_api.core.config import get_settings
    from voter_api.lib.publisher.storage import fetch_manifest

    settings = get_settings()

    if not settings.r2_enabled:
        typer.echo("R2 publishing is not configured.")
        return

    client = _create_r2_client_from_settings(settings)
    assert settings.r2_bucket is not None
    manifest_key = f"{settings.r2_prefix}manifest.json".lstrip("/")

    try:
        manifest = fetch_manifest(client, settings.r2_bucket, manifest_key)
    except Exception as exc:
        typer.echo(f"Error: Failed to fetch manifest from R2: {exc}")
        raise typer.Exit(code=1) from exc

    if manifest is None:
        typer.echo("No datasets have been published yet.")
        return

    typer.echo(f"Published Datasets (last updated: {manifest.published_at.strftime('%Y-%m-%d %H:%M:%S UTC')})")
    typer.echo("─" * 60)

    for name, ds in sorted(manifest.datasets.items()):
        size_mb = ds.file_size_bytes / (1024 * 1024)
        typer.echo(
            f"  {name + '.geojson':30s}  {ds.record_count:>6,} features  {size_mb:>7.1f} MB  "
            f"  {ds.published_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
