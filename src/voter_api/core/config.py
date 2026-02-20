"""Application configuration via Pydantic Settings.

All configuration is loaded from environment variables following 12-factor principles.
"""

import re

from pydantic import Field, field_validator
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
    database_schema: str | None = Field(
        default=None,
        description="PostgreSQL schema for isolated environments (e.g., pr_42)",
    )

    @field_validator("database_schema")
    @classmethod
    def validate_database_schema(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not re.match(r"^[a-z_][a-z0-9_]{0,62}$", v):
            msg = "Invalid database_schema: must match ^[a-z_][a-z0-9_]{0,62}$"
            raise ValueError(msg)
        return v

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
    cors_origin_regex: str = Field(
        default="",
        description="Regex pattern for allowed CORS origins (e.g. https://(.*\\.kerryhatcher\\.com|.*\\.voter-web\\.pages\\.dev))",
    )

    # Election Tracking
    election_refresh_enabled: bool = Field(
        default=True,
        description="Enable background election result refresh loop",
    )
    election_refresh_interval: int = Field(
        default=60,
        description="Seconds between election refresh cycles",
        ge=10,
    )
    election_allowed_domains: str = Field(
        default="results.enr.clarityelections.com,sos.ga.gov,results.sos.ga.gov",
        description="Comma-separated list of allowed domains for election data source URLs",
    )

    @property
    def election_allowed_domain_list(self) -> list[str]:
        """Parse allowed domains string into a lowercase list."""
        if not self.election_allowed_domains.strip():
            return []
        return [d.strip().lower() for d in self.election_allowed_domains.split(",") if d.strip()]

    # Elected Officials Providers
    open_states_api_key: str | None = Field(
        default=None,
        description="Open States API key for state legislator data",
    )
    congress_gov_api_key: str | None = Field(
        default=None,
        description="Congress.gov API key for federal representative data",
    )

    # Environment
    environment: str = Field(
        default="production",
        description="Deployment environment name (e.g. production, dev, staging)",
    )

    # API
    api_v1_prefix: str = Field(
        default="/api/v1",
        description="API version prefix",
    )
    rate_limit_per_minute: int = Field(
        default=200,
        description="Maximum API requests per minute per IP address",
        gt=0,
    )

    # Data Seeding
    data_root_url: str = Field(
        default="https://data.hatchtech.dev/",
        description="Base URL for downloading seed data files (manifest.json + data files)",
    )

    @field_validator("data_root_url")
    @classmethod
    def validate_data_root_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            msg = "data_root_url must use HTTPS"
            raise ValueError(msg)
        return v.rstrip("/") + "/"

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
