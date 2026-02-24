"""Database rebuild CLI command — completely destroys and recreates the database.

.. danger::

    AI agents must NEVER execute this command. It is destructive and
    irreversible. Human operators only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path  # noqa: TC003 - Typer needs Path at runtime
from urllib.parse import urlparse, urlunparse

import typer
from loguru import logger


def _mask_database_url(url: str) -> str:
    """Return *url* with the password replaced by ``****``.

    Args:
        url: A database connection string.

    Returns:
        The URL with the password portion masked.
    """
    parsed = urlparse(url)
    if parsed.password:
        masked = parsed._replace(
            netloc=f"{parsed.username}:****@{parsed.hostname}" + (f":{parsed.port}" if parsed.port else ""),
        )
        return urlunparse(masked)
    return url


def _drop_and_recreate_schema(database_url: str, schema: str | None) -> None:
    """Drop and recreate the target schema using a synchronous connection.

    Args:
        database_url: Async database URL (will be converted to sync).
        schema: Schema name to drop/recreate, or ``None`` for ``public``.
    """
    from sqlalchemy import create_engine, text

    sync_url = database_url.replace("+asyncpg", "").replace("+aiopg", "")
    schema_name = schema or "public"

    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            logger.info(f"Dropping schema {schema_name} CASCADE")
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
            logger.info(f"Creating schema {schema_name}")
            conn.execute(text(f"CREATE SCHEMA {schema_name}"))
            conn.execute(text(f"GRANT ALL ON SCHEMA {schema_name} TO CURRENT_USER"))
    finally:
        engine.dispose()


def rebuild(
    data_root: str | None = typer.Option(
        None,
        "--data-root",
        help="Override the Data Root URL (default: from DATA_ROOT_URL env var)",
    ),
    data_dir: Path = typer.Option(
        "data",
        "--data-dir",
        help="Local directory for downloaded files",
    ),
    category: list[str] | None = typer.Option(
        None,
        "--category",
        help="Filter seed categories: boundaries, voters, county-districts (repeatable)",
    ),
    skip_checksum: bool = typer.Option(
        False,
        "--skip-checksum",
        help="Skip SHA512 checksum verification during seed",
    ),
    max_voters: int | None = typer.Option(
        None,
        "--max-voters",
        help="Limit total voter records imported (e.g., 10000 for preview environments)",
    ),
    skip_seed: bool = typer.Option(
        False,
        "--skip-seed",
        help="Skip the seed/import phase (only reset schema and run migrations)",
    ),
) -> None:
    """Completely destroy and rebuild the database (schema drop + migrate + seed).

    .. danger::

        AI agents must NEVER run this command. It is destructive and
        irreversible. Human operators only.

    This command:
      1. Drops the target schema (CASCADE) and recreates it
      2. Runs all Alembic migrations (upgrade head)
      3. Optionally runs the full seed/import pipeline

    Two interactive confirmations are required before any destructive
    action is taken.
    """
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    from voter_api.core.config import get_settings

    settings = get_settings()
    masked_url = _mask_database_url(settings.database_url)
    schema_name = settings.database_schema or "public"

    # --- Display target ---
    typer.echo(f"\nTarget database: {masked_url}")
    typer.echo(f"Target schema:   {schema_name}")
    typer.echo("")

    # --- Confirmation 1 ---
    if not typer.confirm(
        "Are you sure you want to completely destroy and rebuild this database? This is IRREVERSIBLE.",
        default=False,
    ):
        typer.echo("Aborted.")
        raise typer.Exit(code=0)

    # --- Confirmation 2 ---
    typer.echo("")
    typer.echo("WARNING: Double-check the target database above. AI agents must NEVER run this command.")
    if not typer.confirm("Are you REALLY sure?", default=False):
        typer.echo("Aborted.")
        raise typer.Exit(code=0)

    typer.echo("")

    # --- Step 1: Drop and recreate schema ---
    typer.echo("Step 1/3: Dropping and recreating schema...")
    _drop_and_recreate_schema(settings.database_url, settings.database_schema)
    typer.echo(f"  Schema '{schema_name}' recreated.")

    # --- Step 2: Run migrations ---
    typer.echo("Step 2/3: Running Alembic migrations...")
    alembic_config = AlembicConfig("alembic.ini")
    alembic_command.upgrade(alembic_config, "head")
    typer.echo("  Migrations complete.")

    # --- Step 3: Seed (optional) ---
    if skip_seed:
        typer.echo("Step 3/3: Skipped (--skip-seed).")
        typer.echo("\nRebuild complete (schema reset + migrations only).")
        return

    typer.echo("Step 3/3: Running seed/import pipeline...")

    from voter_api.cli.seed_cmd import _CATEGORY_MAP, _VALID_CATEGORIES, _run_seed, _validate_data_root

    # Validate data_root the same way the seed command does
    data_root = _validate_data_root(data_root)

    # Validate categories
    category_filters = None
    if category:
        category_filters = set()
        for cat in category:
            if cat not in _CATEGORY_MAP:
                typer.echo(
                    f"Error: Invalid category '{cat}'. Valid options: {_VALID_CATEGORIES}",
                    err=True,
                )
                raise typer.Exit(code=1)
            category_filters.add(_CATEGORY_MAP[cat])

    asyncio.run(
        _run_seed(
            data_root=data_root,
            data_dir=data_dir,
            category_filters=category_filters,
            download_only=False,
            fail_fast=False,
            skip_checksum=skip_checksum,
            max_voters=max_voters,
        )
    )

    typer.echo("\nRebuild complete.")
