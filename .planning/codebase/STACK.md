# Technology Stack

**Analysis Date:** 2026-03-13

## Languages

**Primary:**
- Python 3.13 - All application code under `src/voter_api/`

**Secondary:**
- SQL (PostGIS dialect) - Database migrations in `alembic/versions/` (50 migrations)

## Runtime

**Environment:**
- CPython 3.13 (pinned via `.python-version`)

**Package Manager:**
- uv (astral-sh) - all commands must be prefixed with `uv run`
- Lockfile: `uv.lock` (present and committed)
- Build backend: hatchling (`pyproject.toml`)

## Frameworks

**Core:**
- FastAPI >= 0.115.0 - async HTTP API framework; app factory at `src/voter_api/main.py`
- Typer >= 0.15.0 - CLI framework; entrypoint at `src/voter_api/cli/app.py`

**ORM / Database:**
- SQLAlchemy 2.x (asyncio) >= 2.0.0 - async ORM and Core; session management in `src/voter_api/core/database.py`
- GeoAlchemy2 >= 0.15.0 - PostGIS geometry column types
- asyncpg >= 0.30.0 - async PostgreSQL driver
- Alembic >= 1.14.0 - schema migrations; config at `alembic.ini`

**Validation / Settings:**
- Pydantic v2 >= 2.0.0 - request/response schemas in `src/voter_api/schemas/`
- pydantic-settings >= 2.0.0 - 12-factor config from env vars; `src/voter_api/core/config.py`

**Geospatial:**
- Shapely >= 2.0.0 - geometry operations
- GeoPandas >= 1.0.0 - shapefile ingestion
- pyogrio >= 0.10.0 - fast shapefile I/O backend for GeoPandas

**Data Processing:**
- Pandas >= 2.2.0 - CSV parsing and batch transformation
- openpyxl ~= 3.1.5 - XLSX file reading (election calendar)
- pdfplumber >= 0.11.9 - PDF parsing (election calendar)
- beautifulsoup4 >= 4.14.3 + lxml >= 6.0.2 - HTML parsing (election calendar)

**Auth / Security:**
- PyJWT >= 2.9.0 - JWT creation and validation; `src/voter_api/core/security.py`
- bcrypt >= 5.0.0 - password hashing
- cryptography >= 46.0.5 - Fernet encryption for TOTP secrets at rest
- pyotp >= 2.9.0 - TOTP generation and verification; `src/voter_api/lib/totp/`
- webauthn >= 2.0 (py-webauthn) - WebAuthn/passkey ceremonies; `src/voter_api/lib/passkey/`
- segno >= 1.6.6 - QR code generation for TOTP provisioning URIs

**HTTP Client:**
- httpx >= 0.28.0 - async HTTP for geocoder providers, election result fetching

**Email:**
- mailgun >= 1.6.0 - Mailgun API client; `src/voter_api/lib/mailer/`
- Jinja2 >= 3.1.0 - email template rendering

**Storage:**
- boto3 >= 1.42.47 - AWS/Cloudflare R2 S3-compatible object storage; `src/voter_api/lib/publisher/`
- aiofiles >= 25.1.0 - async file I/O for meeting attachments and exports

**AI:**
- anthropic >= 0.84.0 - Anthropic SDK for AI-assisted contest name resolution during candidate import

**Utilities:**
- Loguru >= 0.7.0 - structured logging; configured in `src/voter_api/core/logging.py`
- tqdm >= 4.67.0 - progress bars in CLI commands
- python-dateutil >= 2.9.0 - flexible date parsing for voter records
- email-validator >= 2.3.0 - email format validation in Pydantic schemas
- python-multipart >= 0.0.18 - multipart file uploads

**Testing:**
- pytest >= 8.0.0 - test runner; config in `pyproject.toml` `[tool.pytest.ini_options]`
- pytest-asyncio >= 0.25.0 - async test support; `asyncio_mode = "auto"`
- pytest-cov >= 6.0.0 - coverage reporting
- aiosqlite >= 0.22.1 - in-memory SQLite for unit/integration tests
- moto[s3] >= 5.1.21 - AWS/R2 mock for storage tests
- pytest-httpx >= 0.36.0 - httpx request mocking
- time-machine >= 3.2.0 - datetime mocking in tests
- mypy >= 1.14.0 - static type checking
- ruff >= 0.9.0 - linting and formatting (replaces flake8 + isort + black)
- pip-audit >= 2.7.0 - dependency vulnerability auditing
- bandit >= 1.9.3 - security linting

## Key Dependencies

**Critical:**
- `fastapi` - entire HTTP API layer
- `sqlalchemy[asyncio]` + `asyncpg` - all database access; no raw SQL in application code
- `geoalchemy2` + `shapely` - geospatial point-in-polygon analysis
- `pydantic` + `pydantic-settings` - request validation and 12-factor config
- `alembic` - all schema changes must go through migrations

**Infrastructure:**
- `boto3` - Cloudflare R2 publishing for public GeoJSON datasets
- `httpx` - async HTTP client used by geocoder providers (Census, Google, Geocodio, etc.)
- `anthropic` - AI contest name matching during candidate CSV import

## Configuration

**Environment:**
- All config via environment variables, loaded through `src/voter_api/core/config.py` (Pydantic `BaseSettings`)
- `.env` file supported for local development (not committed)
- `.env.example` documents all required variables
- `ENV` file committed to repo — contains piku/nginx deployment defaults and non-secret config

**Required at runtime:**
- `DATABASE_URL` — PostgreSQL+asyncpg connection string
- `JWT_SECRET_KEY` — minimum 32 characters

**Optional but feature-enabling:**
- `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `MAILGUN_FROM_EMAIL` — must all be set together or none
- `TOTP_SECRET_ENCRYPTION_KEY` — Fernet key for TOTP at-rest encryption
- `GEOCODER_GOOGLE_API_KEY`, `GEOCODER_GEOCODIO_API_KEY`, `GEOCODER_MAPBOX_API_KEY` — geocoding providers
- `OPEN_STATES_API_KEY`, `CONGRESS_GOV_API_KEY` — elected officials data
- `ANTHROPIC_API_KEY` — AI-assisted candidate import
- `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` — object storage publishing
- `WEBAUTHN_RP_ID`, `WEBAUTHN_ORIGIN` — passkey configuration

**Build:**
- `pyproject.toml` — project metadata, dependencies, tool configs (ruff, mypy, pytest)
- `Dockerfile` — multi-stage build; builder uses `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`; runtime on `python:3.13-slim-bookworm` with GDAL/GEOS/PROJ native libs
- `docker-compose.yml` — local dev stack (`postgis/postgis:15-3.4` + api container)

## Platform Requirements

**Development:**
- Python 3.13 (via uv auto-download or system install)
- PostgreSQL 15+ with PostGIS 3.4 extension (or `docker compose up -d db`)
- GDAL, GEOS, PROJ native libraries (for Shapely/GeoPandas; installed in Dockerfile)

**Production:**
- Deployment target: piku (PaaS on `hatchweb.tailb56d83.ts.net`)
- Web server: uvicorn behind nginx; nginx proxied via Cloudflare Tunnel (TLS at edge)
- Process: `web: exec uvicorn --factory voter_api.main:create_app --host 0.0.0.0 --port $PORT` (`Procfile`)
- Migrations run automatically on deploy: `release: voter-api db upgrade` (`Procfile`)
- Docker image also published to GHCR for Kubernetes/ArgoCD preview environments (`.github/workflows/build-push.yaml`)

---

*Stack analysis: 2026-03-13*
