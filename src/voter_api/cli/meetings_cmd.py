"""CLI commands for meeting record management.

Provides the seed-types command to populate default governing body types.
"""

import asyncio

import typer
from loguru import logger

meetings_app = typer.Typer()

DEFAULT_TYPES = [
    ("County Commission", "Governing body of a county"),
    ("City Council", "Legislative body of a city or municipality"),
    ("School Board", "Governing body overseeing a public school district"),
    ("Planning Commission", "Advisory body for land use and zoning decisions"),
    ("Water Authority", "Governing body for water and sewer services"),
    ("Housing Authority", "Governing body for public housing programs"),
    ("Transit Authority", "Governing body for public transportation services"),
]


@meetings_app.command("seed-types")
def seed_types() -> None:
    """Seed default governing body types (idempotent, skips existing)."""
    asyncio.run(_seed_types_impl())


async def _seed_types_impl() -> None:
    """Async implementation of the seed-types command."""
    from voter_api.core.config import get_settings
    from voter_api.core.database import dispose_engine, get_session_factory, init_engine
    from voter_api.core.logging import setup_logging
    from voter_api.services.governing_body_type_service import create_type

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine(settings.database_url, echo=False)

    try:
        factory = get_session_factory()
        created = 0
        skipped = 0

        async with factory() as session:
            for name, description in DEFAULT_TYPES:
                try:
                    await create_type(session, name=name, description=description)
                    created += 1
                    typer.echo(f"  Created: {name}")
                except ValueError:
                    skipped += 1
                    logger.debug(f"Skipped existing type: {name}")

        typer.echo(f"\nSeed complete: {created} created, {skipped} skipped")
    finally:
        await dispose_engine()
