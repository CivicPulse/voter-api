"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables following 12-factor principles.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = Field(
        description="PostgreSQL+PostGIS async connection string",
    )

    # JWT
    jwt_secret_key: str = Field(description="Secret key for signing JWTs")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration in minutes",
        gt=0,
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration in days",
        gt=0,
    )

    # Geocoding
    geocoder_default_provider: str = Field(
        default="census",
        description="Default geocoding provider",
    )
    geocoder_batch_size: int = Field(
        default=100,
        description="Records per geocoding batch",
        gt=0,
    )
    geocoder_rate_limit_per_second: int = Field(
        default=10,
        description="Rate limit for geocoder API calls per second",
        gt=0,
    )

    # Import
    import_batch_size: int = Field(
        default=1000,
        description="Records per import batch",
        gt=0,
    )

    # Export
    export_dir: str = Field(
        default="./exports",
        description="Directory for export output files",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # CORS
    cors_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins",
    )

    # API
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="API version prefix",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins string into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


def get_settings() -> Settings:
    """Create and return application settings."""
    return Settings()  # type: ignore[call-arg]
