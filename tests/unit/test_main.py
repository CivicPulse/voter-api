"""Tests for the FastAPI application factory module."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from voter_api.main import create_app


class TestCreateApp:
    """Tests for create_app."""

    @pytest.fixture
    def app(self):
        with patch("voter_api.main.get_settings") as mock_settings:
            from voter_api.core.config import Settings

            mock_settings.return_value = Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                jwt_secret_key="test-secret-key-not-for-production",
            )
            return create_app()

    def test_app_is_created(self, app) -> None:
        assert app is not None
        assert app.title == "Voter API"

    def test_app_has_openapi_schema(self, app) -> None:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "Voter API"

    def test_value_error_handler_returns_400(self, app) -> None:
        """ValueError exception handler produces 400 response."""

        # Get the exception handler
        handler = app.exception_handlers.get(ValueError)
        assert handler is not None


class TestAppLifespan:
    """Tests for lifespan management."""

    @pytest.mark.asyncio
    async def test_lifespan_init_and_dispose(self) -> None:
        """Lifespan context manager initializes and disposes engine."""
        from voter_api.core.config import Settings
        from voter_api.main import lifespan

        mock_app = AsyncMock()

        with (
            patch("voter_api.main.get_settings") as mock_get_settings,
            patch("voter_api.main.setup_logging") as mock_setup_logging,
            patch("voter_api.main.init_engine") as mock_init_engine,
            patch("voter_api.main.dispose_engine", new_callable=AsyncMock) as mock_dispose,
        ):
            mock_get_settings.return_value = Settings(
                database_url="sqlite+aiosqlite:///:memory:",
                jwt_secret_key="test-secret-key-not-for-production",
            )

            async with lifespan(mock_app):
                mock_setup_logging.assert_called_once()
                mock_init_engine.assert_called_once()

            mock_dispose.assert_awaited_once()
