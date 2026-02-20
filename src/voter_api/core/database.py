"""Async database engine and session management.

Provides async engine creation, session factory, and lifecycle helpers
using SQLAlchemy 2.x with asyncpg.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the current async engine.

    Raises:
        RuntimeError: If the engine has not been initialized.
    """
    if _engine is None:
        msg = "Database engine not initialized. Call init_engine() first."
        raise RuntimeError(msg)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the current session factory.

    Raises:
        RuntimeError: If the engine has not been initialized.
    """
    if _session_factory is None:
        msg = "Session factory not initialized. Call init_engine() first."
        raise RuntimeError(msg)
    return _session_factory


def init_engine(database_url: str, *, schema: str | None = None, **kwargs: object) -> AsyncEngine:
    """Create and store the async engine and session factory.

    Args:
        database_url: PostgreSQL async connection string.
        schema: Optional PostgreSQL schema for isolated environments.
        **kwargs: Additional arguments passed to create_async_engine.

    Returns:
        The created async engine.
    """
    global _engine, _session_factory  # noqa: PLW0603
    if schema is not None:
        connect_args = kwargs.pop("connect_args", {})
        if not isinstance(connect_args, dict):
            msg = "connect_args must be a dict"
            raise TypeError(msg)
        connect_args["options"] = f"-c search_path={schema},public"
        kwargs["connect_args"] = connect_args
    # Only set pool defaults for connection-pooled engines (not SQLite/StaticPool)
    uses_static_pool = kwargs.get("poolclass") is StaticPool or "sqlite" in database_url
    if not uses_static_pool:
        kwargs.setdefault("pool_size", 10)
        kwargs.setdefault("max_overflow", 5)
    _engine = create_async_engine(database_url, **kwargs)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    """Dispose of the async engine and release connections."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
