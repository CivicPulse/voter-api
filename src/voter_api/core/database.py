"""Async database engine and session management.

Provides async engine creation, session factory, and lifecycle helpers
using SQLAlchemy 2.x with asyncpg.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

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


def init_engine(database_url: str, **kwargs: object) -> AsyncEngine:
    """Create and store the async engine and session factory.

    Args:
        database_url: PostgreSQL async connection string.
        **kwargs: Additional arguments passed to create_async_engine.

    Returns:
        The created async engine.
    """
    global _engine, _session_factory  # noqa: PLW0603
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
