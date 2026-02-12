"""Alembic environment configuration for async SQLAlchemy migrations."""

import asyncio
from logging.config import fileConfig

# Register GeoAlchemy2 types for spatial column support in autogenerate
import geoalchemy2  # noqa: F401
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from voter_api.core.config import get_settings
from voter_api.models.analysis_result import AnalysisResult  # noqa: F401
from voter_api.models.analysis_run import AnalysisRun  # noqa: F401
from voter_api.models.audit_log import AuditLog  # noqa: F401
from voter_api.models.base import Base

# Import all models so they are registered with Base.metadata
from voter_api.models.boundary import Boundary  # noqa: F401
from voter_api.models.export_job import ExportJob  # noqa: F401
from voter_api.models.geocoded_location import GeocodedLocation  # noqa: F401
from voter_api.models.geocoder_cache import GeocoderCache  # noqa: F401
from voter_api.models.geocoding_job import GeocodingJob  # noqa: F401
from voter_api.models.import_job import ImportJob  # noqa: F401
from voter_api.models.user import User  # noqa: F401
from voter_api.models.voter import Voter  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from application settings."""
    settings = get_settings()
    return settings.database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    """Run migrations synchronously within a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

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

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
