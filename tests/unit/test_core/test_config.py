"""Unit tests for core configuration module."""

import pytest
from pydantic import ValidationError

from voter_api.core.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings load from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"
        assert settings.jwt_secret_key == "test-secret"

    def test_settings_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default values are applied correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "secret")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_access_token_expire_minutes == 30
        assert settings.jwt_refresh_token_expire_days == 7
        assert settings.geocoder_default_provider == "census"
        assert settings.geocoder_batch_size == 100
        assert settings.import_batch_size == 1000
        assert settings.export_dir == "./exports"
        assert settings.log_level == "INFO"
        assert settings.cors_origins == "*"
        assert settings.api_v1_prefix == "/api/v1"

    def test_cors_origin_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORS origins string is parsed into a list."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "secret")
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://example.com")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.cors_origin_list == ["http://localhost:3000", "http://example.com"]

    def test_validation_positive_integers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Positive integer fields reject zero and negative values."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "secret")
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "0")
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]
