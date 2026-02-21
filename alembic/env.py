"""Alembic environment configuration for async SQLAlchemy migrations."""

import asyncio
from logging.config import fileConfig

# Register GeoAlchemy2 types for spatial column support in autogenerate
import geoalchemy2  # noqa: F401
from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import async_engine_from_config

from voter_api.core.config import get_settings
from voter_api.models.address import Address  # noqa: F401
from voter_api.models.agenda_item import AgendaItem  # noqa: F401
from voter_api.models.analysis_result import AnalysisResult  # noqa: F401
from voter_api.models.analysis_run import AnalysisRun  # noqa: F401
from voter_api.models.audit_log import AuditLog  # noqa: F401
from voter_api.models.base import Base

# Import all models so they are registered with Base.metadata
from voter_api.models.boundary import Boundary  # noqa: F401
from voter_api.models.county_district import CountyDistrict  # noqa: F401
from voter_api.models.county_metadata import CountyMetadata  # noqa: F401
from voter_api.models.elected_official import ElectedOfficial, ElectedOfficialSource  # noqa: F401
from voter_api.models.election import Election, ElectionCountyResult, ElectionResult  # noqa: F401
from voter_api.models.export_job import ExportJob  # noqa: F401
from voter_api.models.geocoded_location import GeocodedLocation  # noqa: F401
from voter_api.models.geocoder_cache import GeocoderCache  # noqa: F401
from voter_api.models.geocoding_job import GeocodingJob  # noqa: F401
from voter_api.models.governing_body import GoverningBody  # noqa: F401
from voter_api.models.governing_body_type import GoverningBodyType  # noqa: F401
from voter_api.models.import_job import ImportJob  # noqa: F401
from voter_api.models.meeting import Meeting  # noqa: F401
from voter_api.models.meeting_attachment import MeetingAttachment  # noqa: F401
from voter_api.models.meeting_video_embed import MeetingVideoEmbed  # noqa: F401
from voter_api.models.precinct_metadata import PrecinctMetadata  # noqa: F401
from voter_api.models.user import User  # noqa: F401
from voter_api.models.voter import Voter  # noqa: F401
from voter_api.models.voter_history import VoterHistory  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from application settings."""
    settings = get_settings()
    return settings.database_url


def _get_schema() -> str | None:
    """Get database schema from application settings."""
    settings = get_settings()
    return settings.database_schema


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    schema = _get_schema()
    configure_kwargs: dict[str, object] = {
        "url": url,
        "target_metadata": target_metadata,
        "literal_binds": True,
        "dialect_opts": {"paramstyle": "named"},
        "compare_type": True,
    }
    if schema is not None:
        configure_kwargs["version_table_schema"] = schema
    context.configure(**configure_kwargs)

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """Run migrations synchronously within a connection."""
    schema = _get_schema()
    configure_kwargs: dict[str, object] = {
        "connection": connection,
        "target_metadata": target_metadata,
        "compare_type": True,
    }
    if schema is not None:
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        configure_kwargs["version_table_schema"] = schema
    context.configure(**configure_kwargs)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    schema = _get_schema()
    async with connectable.connect() as connection:
        if schema is not None:
            await connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await connection.commit()
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
