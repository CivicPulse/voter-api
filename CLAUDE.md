# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

voter-api is a Python/FastAPI REST API + CLI for managing Georgia Secretary of State voter data with geospatial capabilities. It ingests voter CSV files, geocodes addresses, imports district/precinct boundary shapefiles, performs point-in-polygon analysis to detect registration-location mismatches, and supports search and bulk export. No frontend — API and CLI only.

**Status**: Active development. Implementation follows the task plan in `specs/001-voter-data-management/tasks.md`. Source code lives under `src/voter_api/`.

## Tech Stack

- **Python 3.13** (see `.python-version`)
- **FastAPI** (async web framework)
- **SQLAlchemy 2.x** (async) + **GeoAlchemy2** (ORM + geospatial)
- **PostgreSQL 15+ / PostGIS 3.x** (database)
- **Alembic** (migrations)
- **Pydantic v2** (validation, schemas, settings)
- **Typer** (CLI)
- **Loguru** (logging)
- **Pandas** (data processing)
- **Docker + docker-compose** (containerization, local dev)

## Commands

```bash
# Install dependencies
uv sync

# Run the dev server
uv run voter-api serve --reload

# Run all tests
uv run pytest

# Run tests with coverage (90% threshold required)
uv run pytest --cov=voter_api --cov-report=term-missing

# Run a single test file
uv run pytest tests/unit/lib/test_geocoder/test_cache.py

# Run tests matching a keyword
uv run pytest -k "test_import"

# Lint and format check (must pass before every commit)
uv run ruff check .
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check . --fix
uv run ruff format .

# Database migrations
uv run voter-api db upgrade
uv run voter-api db downgrade
```

## Architecture

The project follows a **Library-First Architecture** — all features are implemented as standalone, independently testable libraries before integration.

### Layer Structure (planned)

```
src/voter_api/
├── core/        # Config (Pydantic Settings), database engine, security (JWT), logging
├── models/      # SQLAlchemy + GeoAlchemy2 ORM models
├── schemas/     # Pydantic v2 request/response schemas
├── api/v1/      # FastAPI route handlers (HTTP concerns only)
├── services/    # Business logic orchestration (calls libraries + DB)
├── lib/         # Standalone libraries (the core of the codebase)
│   ├── geocoder/        # Pluggable geocoding with provider abstraction + caching
│   ├── importer/        # CSV parsing, validation, diff generation
│   ├── exporter/        # CSV, JSON, GeoJSON export writers
│   ├── analyzer/        # Point-in-polygon, registration vs physical comparison
│   └── boundary_loader/ # Shapefile + GeoJSON ingestion
└── cli/         # Typer CLI commands (calls services)
```

**Data flow**: CLI/API routes → Services → Libraries + Database

Each library in `lib/` has an explicit public API via `__init__.py` exports and must be usable without the rest of the application.

### Test Organization

```
tests/
├── unit/           # Library and schema tests (no DB)
├── integration/    # API, database, and CLI tests (requires PostGIS)
└── contract/       # OpenAPI contract tests
```

## Key Conventions

- **Never use system python** — always prefix with `uv run` (e.g., `uv run pytest`, `uv run python`)
- **Package management** — `uv add <pkg>`, `uv add --dev <pkg>`, `uv remove <pkg>`
- **Conventional Commits** — all commit messages must follow the spec (see `docs/convential_commits.md`)
- **12-factor config** — all configuration via environment variables, validated by Pydantic Settings; `.env.example` documents all required vars
- **Type hints** on all functions/classes; **Google-style docstrings** on all public APIs
- **Ruff** for both linting and formatting — must pass with zero violations before commit
- **JWT-only auth** with role-based access control (admin/analyst/viewer)
- **No raw SQL** — SQLAlchemy ORM/Core exclusively
- **API versioning** via URL prefix (`/api/v1/`)
- **Branch strategy** — all work on feature branches, never directly on `main`
- **Commit cadence** — commit to git after completing each task, story, or phase; do not accumulate large uncommitted changesets
- **Lint before commit** — always run `uv run ruff check .` and `uv run ruff format --check .` before committing

## Reference Documents

- `specs/001-voter-data-management/spec.md` — full feature specification with user stories
- `specs/001-voter-data-management/plan.md` — implementation plan with project structure
- `specs/001-voter-data-management/data-model.md` — database schema design
- `specs/001-voter-data-management/contracts/openapi.yaml` — full OpenAPI 3.1 spec
- `specs/001-voter-data-management/quickstart.md` — setup instructions and CLI reference
- `.specify/memory/constitution.md` — project constitution (binding principles)
- `docs/convential_commits.md` — Conventional Commits reference

## Data Directory

`data/` contains Georgia boundary shapefiles and district data (ZIP archives with SHA512 checksums). These are input data files, not generated artifacts.

<!-- MANUAL ADDITIONS START -->

## Deployment (Piku)

The app deploys to a piku server via `git push piku main`. Configuration lives in two root files:

- **`Procfile`** — defines `release` (Alembic migrations) and `web` (uvicorn ASGI) workers
- **`ENV`** — piku/nginx settings and app environment variables; secrets should be set on the server via `piku config:set` rather than committed here

**Dependency detection caveat**: Piku detects Python projects via `requirements.txt` or `pyproject.toml`. Its `pyproject.toml` support documents poetry and uv but does not explicitly cover hatchling as a build backend. If piku fails to install dependencies on deploy, generate a `requirements.txt` fallback with `uv export --no-hashes > requirements.txt` and commit it. Piku will prefer `requirements.txt` when present.

<!-- MANUAL ADDITIONS END -->

## Recent Changes
- 002-static-dataset-publish: Added Python 3.13 + FastAPI, SQLAlchemy 2.x + GeoAlchemy2, Typer, Pydantic v2, boto3 (new), Loguru

### 002-static-dataset-publish

**County Metadata** — Census TIGER/Line attributes are stored in a dedicated `county_metadata` table (migration 011), keyed by FIPS GEOID. Populated automatically during `import all-boundaries` from the same county shapefile. The boundary detail endpoint (`GET /api/v1/boundaries/{id}`) includes a `county_metadata` field when `boundary_type == "county"`, with typed fields like FIPS codes, statistical area codes, land/water area, and computed km² values. Designed as the join point for future Census ACS demographic enrichment.

Key files:

- `src/voter_api/models/county_metadata.py` — ORM model (18 typed columns)
- `src/voter_api/services/county_metadata_service.py` — import (upsert by GEOID) and query

## Active Technologies
- Python 3.13 + FastAPI, SQLAlchemy 2.x + GeoAlchemy2, Typer, Pydantic v2, boto3 (new), Loguru (002-static-dataset-publish)
- PostgreSQL + PostGIS (read-only for this feature), Cloudflare R2 (new, S3-compatible) (002-static-dataset-publish)
