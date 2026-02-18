"""Tests for the database engine and session management module."""

from unittest.mock import MagicMock, patch

import pytest

import voter_api.core.database as db_module
from voter_api.core.database import dispose_engine, get_engine, get_session_factory, init_engine


class TestGetEngine:
    """Tests for get_engine."""

    def test_raises_when_not_initialized(self) -> None:
        # Save and clear module state
        original_engine = db_module._engine
        db_module._engine = None
        try:
            with pytest.raises(RuntimeError, match="Database engine not initialized"):
                get_engine()
        finally:
            db_module._engine = original_engine

    @pytest.mark.asyncio
    async def test_returns_engine_when_initialized(self) -> None:
        engine = init_engine("sqlite+aiosqlite:///:memory:")
        try:
            assert get_engine() is engine
        finally:
            await dispose_engine()


class TestGetSessionFactory:
    """Tests for get_session_factory."""

    def test_raises_when_not_initialized(self) -> None:
        original_factory = db_module._session_factory
        db_module._session_factory = None
        try:
            with pytest.raises(RuntimeError, match="Session factory not initialized"):
                get_session_factory()
        finally:
            db_module._session_factory = original_factory


class TestInitEngine:
    """Tests for init_engine."""

    @pytest.mark.asyncio
    async def test_creates_engine_and_factory(self) -> None:
        engine = init_engine("sqlite+aiosqlite:///:memory:")
        try:
            assert engine is not None
            factory = get_session_factory()
            assert factory is not None
        finally:
            await dispose_engine()

    def test_init_engine_without_schema(self) -> None:
        """init_engine without schema does not inject connect_args."""
        with patch("voter_api.core.database.create_async_engine", return_value=MagicMock()) as mock_create:
            init_engine("postgresql+asyncpg://localhost/db", echo=False)
            mock_create.assert_called_once_with("postgresql+asyncpg://localhost/db", echo=False)

    def test_init_engine_with_schema(self) -> None:
        """init_engine with schema injects connect_args with search_path."""
        with patch("voter_api.core.database.create_async_engine", return_value=MagicMock()) as mock_create:
            init_engine("postgresql+asyncpg://localhost/db", schema="pr_42", echo=False)
            mock_create.assert_called_once_with(
                "postgresql+asyncpg://localhost/db",
                echo=False,
                connect_args={"options": "-c search_path=pr_42,public"},
            )


class TestDisposeEngine:
    """Tests for dispose_engine."""

    @pytest.mark.asyncio
    async def test_disposes_engine(self) -> None:
        init_engine("sqlite+aiosqlite:///:memory:")
        await dispose_engine()
        assert db_module._engine is None
        assert db_module._session_factory is None

    @pytest.mark.asyncio
    async def test_dispose_when_no_engine(self) -> None:
        original = db_module._engine
        db_module._engine = None
        try:
            await dispose_engine()  # Should not raise
        finally:
            db_module._engine = original
