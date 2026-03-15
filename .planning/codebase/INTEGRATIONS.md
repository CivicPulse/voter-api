# External Integrations

**Analysis Date:** 2026-03-13

## APIs & External Services

**Geocoding Providers (pluggable, cascading fallback):**
- US Census Bureau Geocoding API - always-enabled free provider; no API key required
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/census.py`
  - Auth: none
- OpenStreetMap Nominatim - free, requires email per usage policy
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/nominatim.py`
  - Auth: `GEOCODER_NOMINATIM_EMAIL` (not a key — identifies the requester)
- Google Maps Geocoding API - paid, batch not supported
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/google_maps.py`
  - Auth: `GEOCODER_GOOGLE_API_KEY`
- Geocodio - paid, supports batch up to 10,000 records
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/geocodio.py`
  - Auth: `GEOCODER_GEOCODIO_API_KEY`
- Mapbox Geocoding API - paid, batch up to 1,000 records
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/mapbox.py`
  - Auth: `GEOCODER_MAPBOX_API_KEY`
- Photon (Komoot) - free, self-hostable OpenStreetMap geocoder
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/geocoder/photon.py`
  - Auth: none; base URL configurable via `GEOCODER_PHOTON_BASE_URL`

Fallback order controlled by `GEOCODER_FALLBACK_ORDER` env var (default: `census,nominatim,geocodio,mapbox,google,photon`). Provider registry and factory at `src/voter_api/lib/geocoder/__init__.py`.

**Elected Officials Data Providers:**
- Open States API - state legislator data
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/officials/open_states.py`
  - Auth: `OPEN_STATES_API_KEY`
- Congress.gov API - federal representative data
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/officials/congress_gov.py`
  - Auth: `CONGRESS_GOV_API_KEY`

Provider registry in `src/voter_api/lib/officials/__init__.py`.

**Georgia Secretary of State Election Data:**
- SoS election results feed (JSON) - `results.enr.clarityelections.com`, `sos.ga.gov`, `results.sos.ga.gov`
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/election_tracker/fetcher.py`
  - Auth: none (public)
  - Domain allowlist controlled by `ELECTION_ALLOWED_DOMAINS` env var
  - Background refresh loop in `src/voter_api/services/election_service.py` (interval: `ELECTION_REFRESH_INTERVAL`)

**AI / LLM:**
- Anthropic Claude API - AI-assisted contest name resolution during candidate CSV import
  - SDK/Client: `anthropic` Python SDK
  - Auth: `ANTHROPIC_API_KEY` (Pydantic `SecretStr`)
  - Used in candidate import pipeline; `src/voter_api/lib/candidate_importer/`

**Email Delivery:**
- Mailgun - transactional email for password resets and user invitations
  - SDK/Client: `mailgun` Python package
  - Auth: `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `MAILGUN_FROM_EMAIL` (all three required together)
  - Template engine: Jinja2; templates in `src/voter_api/lib/mailer/templates/`
  - Implementation: `src/voter_api/lib/mailer/mailer.py` (`MailgunMailer`)

**Seed Data Downloads:**
- Internal data CDN (`DATA_ROOT_URL`, default `https://data.hatchtech.dev/`) - downloads boundary shapefiles and election seed data
  - SDK/Client: direct `httpx` calls in `src/voter_api/lib/data_loader/downloader.py`
  - Auth: none (must use HTTPS)
  - Fetches `manifest.json` then individual files with SHA512 checksum verification

## Data Storage

**Databases:**
- PostgreSQL 15+ with PostGIS 3.4 extension
  - Connection: `DATABASE_URL` env var (format: `postgresql+asyncpg://user:pass@host:port/dbname`)
  - Optional schema isolation: `DATABASE_SCHEMA` env var (used for preview/PR environments)
  - Client: SQLAlchemy 2.x async ORM + asyncpg driver; engine/session in `src/voter_api/core/database.py`
  - Pool: `pool_size=20`, `max_overflow=10` (production); `StaticPool` for tests
  - Migrations: Alembic; 50 migrations in `alembic/versions/`; applied automatically on deploy via `Procfile` `release` worker
  - ORM models in `src/voter_api/models/` (30+ model files including geospatial `boundary.py`, `geocoded_location.py`)

**File Storage:**
- Cloudflare R2 (S3-compatible) - optional; stores published GeoJSON boundary datasets
  - SDK/Client: `boto3` with custom endpoint `https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`
  - Auth: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`
  - Feature flag: `R2_ENABLED=false` (disabled by default)
  - Implementation: `src/voter_api/lib/publisher/storage.py` (`create_r2_client`, `upload_file`)
  - Manifest TTL configurable via `R2_MANIFEST_TTL` (default 300s)
- Local filesystem - meeting attachments (`MEETING_UPLOAD_DIR`, default `./uploads/meetings`) and export files (`EXPORT_DIR`, default `./exports`)

**Caching:**
- Database-backed geocoder cache - results stored in `geocoder_cache` table (PostGIS); `src/voter_api/lib/geocoder/cache.py`
- In-memory manifest cache for R2 datasets - `ManifestCache` in `src/voter_api/lib/publisher/manifest.py`

## Authentication & Identity

**Auth Provider:** Custom JWT-based implementation (no third-party auth provider)
- Implementation: `src/voter_api/core/security.py`
- Library: PyJWT (HS256 algorithm, configurable via `JWT_ALGORITHM`)
- Tokens: access token (default 30 min, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`) + refresh token (default 7 days, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`)
- Password hashing: bcrypt via `bcrypt` package
- Roles: `admin`, `analyst`, `viewer` (stored in JWT `role` claim)

**Two-Factor Authentication:**
- TOTP (RFC 6238) - pyotp + Fernet encryption of secrets at rest; `src/voter_api/lib/totp/`
  - Encryption key: `TOTP_SECRET_ENCRYPTION_KEY`
  - Lockout: `TOTP_MAX_ATTEMPTS` (default 5), `TOTP_LOCKOUT_MINUTES` (default 15)
  - Models: `src/voter_api/models/totp.py`
- WebAuthn Passkeys - py-webauthn; `src/voter_api/lib/passkey/`
  - Config: `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGIN`
  - Challenge stored in short-lived JWT (5 min) via `create_passkey_challenge_token`
  - Model: `src/voter_api/models/passkey.py`

**Password Reset / Invitations:**
- Token-based; `PasswordResetToken` and `UserInvite` models in `src/voter_api/models/auth_tokens.py`
- Rate limiting: `RESET_RATE_LIMIT_MINUTES` (default 5 min between requests)
- Email delivery via Mailgun integration

## Monitoring & Observability

**Error Tracking:** None detected (no Sentry, Rollbar, or similar)

**Logs:**
- Loguru structured logging; configured in `src/voter_api/core/logging.py`
- Log level: `LOG_LEVEL` env var (default `INFO`; dev default `DEBUG`)
- Optional file logging with 24-hour rotation: `LOG_DIR` env var
- Production logs viewable via: `ssh piku@hatchweb.tailb56d83.ts.net -- logs voter-api`

## CI/CD & Deployment

**Hosting:**
- Primary: piku PaaS on `hatchweb.tailb56d83.ts.net` (Tailscale-accessible server)
  - Dev: `voter-api-dev` app → `https://voteapi-dev.hatchtech.dev`
  - Prod: `voter-api` app → `https://voteapi.civpulse.org`
- Preview: Kubernetes via ArgoCD (for PR preview environments); image from GHCR
- Ingress: Cloudflare Tunnel (terminates TLS at edge; nginx listens only on port 80)

**CI Pipeline:** GitHub Actions (`.github/workflows/`)
- `ci.yml` - lint (`ruff check`), format check (`ruff format`), typecheck (`mypy`), tests with coverage (70% threshold), `pip-audit`
- `e2e.yml` - E2E smoke tests against real PostGIS; triggers on PRs to `main`
- `build-push.yaml` - builds Docker image and pushes to GHCR
- `prod-deploy.yml` - deploys to piku prod after CI passes on `main`; connects via Tailscale + SSH
- `preview-deploy.yml` / `preview-cleanup.yml` / `preview-gc.yml` - PR preview environment lifecycle

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - PostgreSQL+asyncpg connection string
- `JWT_SECRET_KEY` - minimum 32-character secret

**Secrets location:**
- Dev secrets set via `piku config:set voter-api-dev ...` on the server (not committed)
- Prod secrets set via `piku config:set voter-api ...` on the server (not committed)
- CI secrets stored in GitHub Actions repository secrets (`PIKU_SSH_KEY`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`)
- `ENV` file committed to repo contains non-secret defaults and piku/nginx configuration

## Webhooks & Callbacks

**Incoming:** None detected

**Outgoing:**
- Election result fetch loop — `src/voter_api/services/election_service.py` polls SoS feed URLs at configurable interval (`ELECTION_REFRESH_INTERVAL`, default 60s); polls only when `ELECTION_REFRESH_ENABLED=true`

---

*Integration audit: 2026-03-13*
