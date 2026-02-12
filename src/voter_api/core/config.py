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
    jwt_secret_key: str = Field(min_length=32, description="Secret key for signing JWTs (minimum 32 characters)")
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
        default="",
        description="Comma-separated list of allowed CORS origins (must be explicitly configured)",
    )

    # API
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="API version prefix",
    )

    # R2 / S3-Compatible Object Storage
    r2_enabled: bool = Field(
        default=False,
        description="Enable R2/S3 publishing and redirect",
    )
    r2_account_id: str | None = Field(
        default=None,
        description="Cloudflare R2 account ID",
    )
    r2_access_key_id: str | None = Field(
        default=None,
        description="R2 API token access key",
    )
    r2_secret_access_key: str | None = Field(
        default=None,
        description="R2 API token secret key",
    )
    r2_bucket: str | None = Field(
        default=None,
        description="R2 bucket name",
    )
    r2_public_url: str | None = Field(
        default=None,
        description="Public URL prefix for R2 (custom domain or r2.dev URL)",
    )
    r2_prefix: str = Field(
        default="",
        description="Key prefix within the R2 bucket",
    )
    r2_manifest_ttl: int = Field(
        default=300,
        description="Manifest cache TTL in seconds",
        gt=0,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS origins string into a list."""
        if not self.cors_origins.strip():
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def get_settings() -> Settings:
    """Create and return application settings."""
    return Settings()  # type: ignore[call-arg]
