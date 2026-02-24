"""Database rebuild CLI command — completely destroys and recreates the database.

.. danger::

    AI agents must NEVER execute this command. It is destructive and
    irreversible. Human operators only.
"""

from __future__ import annotations

import asyncio
import re
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


async def _seed_preview_user(database_url: str, schema: str | None) -> None:
    """Create an admin user from PREVIEW_API_* env vars if all three are set.

    Idempotent — logs a skip message if the user already exists.

    Args:
        database_url: Async database URL.
        schema: PostgreSQL schema name, or ``None`` for ``public``.
    """
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.schemas.auth import UserCreateRequest
    from voter_api.services.auth_service import create_user

    settings = get_settings()

    if not (settings.preview_api_user and settings.preview_api_email and settings.preview_api_password):
        return

    init_engine(database_url, schema=schema)
    try:
        factory = get_session_factory()
        async with factory() as session:
            request = UserCreateRequest(
                username=settings.preview_api_user,
                email=settings.preview_api_email,
                password=settings.preview_api_password,
                role="admin",
            )
            user = await create_user(session, request)
            logger.info(f"Preview user '{user.username}' created with role 'admin'")
    except ValueError as e:
        if "already exists" in str(e):
            logger.info(f"Preview user '{settings.preview_api_user}' already exists, skipping")
        else:
            raise
    finally:
        await dispose_engine()


async def _drop_and_recreate_schema(database_url: str, schema: str | None) -> None:
    """Drop and recreate the target schema using an async connection.

    Args:
        database_url: Async database URL (e.g. ``postgresql+asyncpg://...``).
        schema: Schema name to drop/recreate, or ``None`` for ``public``.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.schema import CreateSchema, DropSchema

    schema_name = schema or "public"

    # Validate schema name to prevent SQL injection — only allow
    # alphanumeric characters and underscores (valid PostgreSQL identifiers).
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema_name):
        msg = f"Invalid schema name: {schema_name!r}"
        raise ValueError(msg)

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            logger.info(f"Dropping schema {schema_name} CASCADE")
            await conn.execute(DropSchema(schema_name, cascade=True, if_exists=True))
            logger.info(f"Creating schema {schema_name}")
            await conn.execute(CreateSchema(schema_name))
            # No SQLAlchemy construct for GRANT — raw SQL is acceptable here.
            await conn.execute(text(f"GRANT ALL ON SCHEMA {schema_name} TO CURRENT_USER"))
    finally:
        await engine.dispose()


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
        help="Filter seed categories: boundaries, voters, county-districts, voter-history (repeatable)",
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
    election_source: str | None = typer.Option(
        "https://voteapi.civpulse.org",
        "--election-source",
        help="Base URL of the source API to fetch elections from",
    ),
    skip_elections: bool = typer.Option(
        False,
        "--skip-elections",
        help="Skip the election seeding step",
    ),
    skip_seed: bool = typer.Option(
        False,
        "--skip-seed",
        help="Skip the seed/import phase (only reset schema and run migrations)",
    ),
) -> None:
    """Completely destroy and rebuild the database (schema drop + migrate + seed).

    Warning:
        AI agents must NEVER run this command. It is destructive and
        irreversible. Human operators only.

    Args:
        data_root: Override the data root URL.
        data_dir: Local directory for downloaded files.
        category: Optional category filter list.
        skip_checksum: Skip SHA512 checksum verification.
        max_voters: Limit total voter records imported.
        election_source: Base URL for election seed source.
        skip_elections: Skip the election seeding step.
        skip_seed: Skip the seed/import phase.

    Steps:
        1. Drops the target schema (CASCADE) and recreates it.
        2. Runs all Alembic migrations (upgrade head).
        3. Seeds a preview admin user (if PREVIEW_API_* env vars are set).
        4. Optionally runs the full seed/import pipeline.

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
    typer.echo("Step 1/4: Dropping and recreating schema...")
    asyncio.run(_drop_and_recreate_schema(settings.database_url, settings.database_schema))
    typer.echo(f"  Schema '{schema_name}' recreated.")

    # --- Step 2: Run migrations ---
    typer.echo("Step 2/4: Running Alembic migrations...")
    alembic_config = AlembicConfig("alembic.ini")
    alembic_command.upgrade(alembic_config, "head")
    typer.echo("  Migrations complete.")

    # --- Step 3: Seed preview user (if env vars set) ---
    typer.echo("Step 3/4: Seeding preview user...")
    asyncio.run(_seed_preview_user(settings.database_url, settings.database_schema))

    # --- Step 4: Seed (optional) ---
    if skip_seed:
        typer.echo("Step 4/4: Skipped (--skip-seed).")
        typer.echo("\nRebuild complete (schema reset + migrations only).")
        return

    typer.echo("Step 4/4: Running seed/import pipeline...")

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
            election_source=election_source,
            skip_elections=skip_elections,
        )
    )

    typer.echo("\nRebuild complete.")
