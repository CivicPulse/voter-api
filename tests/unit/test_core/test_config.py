"""Unit tests for core configuration module."""

import pytest
from pydantic import ValidationError

from voter_api.core.config import Settings


class TestSettings:
    """Tests for Settings configuration."""

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings load from environment variables."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"
        assert settings.jwt_secret_key == "test-secret-key-that-is-at-least-32-characters-long"

    def test_settings_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default values are applied correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_access_token_expire_minutes == 30
        assert settings.jwt_refresh_token_expire_days == 7
        assert settings.geocoder_default_provider == "census"
        assert settings.geocoder_batch_size == 100
        assert settings.import_batch_size == 5000
        assert settings.export_dir == "./exports"
        assert settings.log_level == "INFO"
        assert settings.cors_origins == ""
        assert settings.api_v1_prefix == "/api/v1"
        assert settings.rate_limit_per_minute == 200

    def test_cors_origin_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORS origins string is parsed into a list."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://example.com")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.cors_origin_list == ["http://localhost:3000", "http://example.com"]

    def test_jwt_secret_key_minimum_length(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JWT secret key must be at least 32 characters."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
        with pytest.raises(ValidationError, match="at least 32 characters"):
            Settings()  # type: ignore[call-arg]

    def test_validation_positive_integers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Positive integer fields reject zero and negative values."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "0")
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_validation_rate_limit_positive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rate limit per minute must be a positive integer."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
        with pytest.raises(ValidationError):
            Settings()  # type: ignore[call-arg]

    def test_database_schema_default_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_schema defaults to None."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.database_schema is None

    def test_database_schema_valid_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_schema accepts valid schema names like pr_42."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("DATABASE_SCHEMA", "pr_42")
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.database_schema == "pr_42"

    def test_database_schema_rejects_injection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_schema rejects SQL injection attempts."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("DATABASE_SCHEMA", "pr-42; DROP SCHEMA")
        with pytest.raises(ValidationError, match="Invalid database_schema"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_database_schema_rejects_leading_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """database_schema rejects names starting with a digit."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long")
        monkeypatch.setenv("DATABASE_SCHEMA", "42pr")
        with pytest.raises(ValidationError, match="Invalid database_schema"):
            Settings(_env_file=None)  # type: ignore[call-arg]
