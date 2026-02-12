# Quickstart: Voter Data Management

**Branch**: `001-voter-data-management` | **Date**: 2026-02-11

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker & Docker Compose (for PostGIS database)
- Git

## Setup (3 commands)

```bash
# 1. Clone and enter the project
git clone <repo-url> voter-api && cd voter-api

# 2. Install dependencies
uv sync

# 3. Start services (PostGIS + API)
docker compose up -d
```

## Alternative: Local Development Without Docker

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your PostgreSQL+PostGIS connection string

# Run database migrations
uv run voter-api db upgrade

# Start the development server
uv run voter-api serve --reload
```

## Environment Configuration

All configuration is via environment variables (12-factor). Copy
`.env.example` and fill in values:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL+PostGIS connection | `postgresql+asyncpg://user:pass@localhost:5432/voter_api` |
| `JWT_SECRET_KEY` | Secret for signing JWTs | (generate with `openssl rand -hex 32`) |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL | `30` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL | `7` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEOCODER_DEFAULT_PROVIDER` | Default geocoding provider | `census` |
| `GEOCODER_BATCH_SIZE` | Records per geocoding batch | `100` |
| `GEOCODER_RATE_LIMIT_PER_SECOND` | Rate limit for provider calls | `10` |
| `IMPORT_BATCH_SIZE` | Records per import batch | `1000` |
| `EXPORT_DIR` | Directory for export files | `./exports` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `*` |
| `API_V1_PREFIX` | API version prefix | `/api/v1` |

## CLI Reference

The CLI is accessed via `uv run voter-api <command>`:

```bash
# Database operations
uv run voter-api db upgrade          # Run pending migrations
uv run voter-api db downgrade        # Rollback last migration
uv run voter-api db current          # Show current migration

# Server
uv run voter-api serve               # Start production server
uv run voter-api serve --reload      # Start dev server with auto-reload

# User management
uv run voter-api user create         # Create a new user (interactive)
uv run voter-api user list           # List all users

# Data import
uv run voter-api import voters <file>          # Import voter CSV
uv run voter-api import boundaries <file> \
    --type congressional --source state         # Import boundary file

# Geocoding
uv run voter-api geocode --county "Fulton"     # Geocode un-geocoded voters
uv run voter-api geocode --provider census \
    --force                                     # Re-geocode all voters
uv run voter-api geocode manual <voter_id> \
    --lat 33.749 --lon -84.388                  # Manual coordinate entry

# Analysis
uv run voter-api analyze --county "Fulton"     # Run location analysis
uv run voter-api analyze --notes "post-redistricting"

# Export
uv run voter-api export --format csv \
    --county "Fulton"                           # Export to CSV
uv run voter-api export --format geojson \
    --match-status mismatch-both                # Export mismatches as GeoJSON
```

## API Endpoints (Summary)

Once the server is running, full interactive API documentation is
available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Authenticate, get JWT |
| GET | `/api/v1/voters` | Search voters |
| GET | `/api/v1/voters/{id}` | Get voter details |
| POST | `/api/v1/imports/voters` | Import voter file |
| POST | `/api/v1/imports/boundaries` | Import boundary file |
| POST | `/api/v1/geocoding/batch` | Trigger batch geocoding |
| GET | `/api/v1/boundaries` | List boundaries |
| GET | `/api/v1/boundaries/containing-point` | Point-in-polygon query |
| POST | `/api/v1/analysis/runs` | Run location analysis |
| GET | `/api/v1/analysis/runs/{id}/results` | View analysis results |
| POST | `/api/v1/exports` | Request data export |
| GET | `/api/v1/exports/{id}/download` | Download export file |
| GET | `/api/v1/health` | Health check (no auth) |

## Docker Compose Services

```yaml
services:
  db:
    image: postgis/postgis:15-3.4
    ports: ["5432:5432"]
    environment:
      POSTGRES_DB: voter_api
      POSTGRES_USER: voter_api
      POSTGRES_PASSWORD: voter_api_dev
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: pg_isready -U voter_api
      interval: 5s
      retries: 5

  api:
    build: .
    ports: ["8000:8000"]
    depends_on:
      db:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://voter_api:voter_api_dev@db:5432/voter_api
    volumes:
      - ./src:/app/src
      - ./exports:/app/exports

volumes:
  pgdata:
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=voter_api --cov-report=term-missing

# Run specific test categories
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/contract/

# Run with verbose output
uv run pytest -v
```

## Typical Workflow

1. **Start services**: `docker compose up -d`
2. **Run migrations**: `uv run voter-api db upgrade`
3. **Create admin user**: `uv run voter-api user create`
4. **Import voter data**: `uv run voter-api import voters data/voters.csv`
5. **Import boundaries**: `uv run voter-api import boundaries data/districts.shp --type congressional`
6. **Geocode addresses**: `uv run voter-api geocode --county "Fulton"`
7. **Run analysis**: `uv run voter-api analyze --county "Fulton"`
8. **Query results via API**: Use Swagger UI at http://localhost:8000/docs
9. **Export data**: `uv run voter-api export --format csv --match-status mismatch-both`

## Project Structure

```text
src/voter_api/
├── main.py          # FastAPI app factory
├── core/            # Config, database, security, logging
├── models/          # SQLAlchemy + GeoAlchemy2 models
├── schemas/         # Pydantic v2 request/response schemas
├── api/v1/          # FastAPI route handlers
├── services/        # Business logic orchestration
├── lib/             # Standalone libraries
│   ├── geocoder/    # Pluggable geocoding with caching
│   ├── importer/    # CSV parsing, validation, diff
│   ├── exporter/    # CSV, JSON, GeoJSON export
│   ├── analyzer/    # Point-in-polygon + comparison
│   └── boundary_loader/  # Shapefile + GeoJSON ingestion
└── cli/             # Typer CLI commands
```
