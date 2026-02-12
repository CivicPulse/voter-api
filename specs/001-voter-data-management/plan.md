# Implementation Plan: Voter Data Management

**Branch**: `001-voter-data-management` | **Date**: 2026-02-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-voter-data-management/spec.md`

## Summary

Build a Python/FastAPI REST API service for managing Georgia Secretary of State
voter data with geospatial capabilities. The system ingests voter CSV files,
geocodes addresses via pluggable providers, imports district/precinct boundary
data (shapefile/GeoJSON), performs point-in-polygon analysis to detect
registration-location mismatches, and supports search, export, and historical
analysis snapshots. All functionality is exposed through REST API and CLI (no
frontend). Authentication is JWT-only with role-based access control across
two data sensitivity tiers. Built on PostgreSQL/PostGIS with SQLAlchemy 2.x
async, following library-first architecture principles.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), GeoAlchemy2,
Pydantic v2, Typer, Loguru, Pandas, Alembic, PyJWT (python-jose),
httpx, Fiona/pyshp (shapefile), GeoJSON
**Storage**: PostgreSQL 15+ with PostGIS 3.x
**Testing**: pytest with pytest-cov, pytest-asyncio, httpx (AsyncClient)
**Target Platform**: Linux server (Docker containers, docker-compose for local dev)
**Project Type**: single (API + library + CLI, no frontend)
**Performance Goals**: 500K voter import <30min, voter search <2s p95,
analysis for 500K voters <60min, bulk export 500K <15min
**Constraints**: 90% test coverage, all code type-hinted + docstrings,
ruff clean, JWT-only auth, 12-factor config, library-first
**Scale/Scope**: 2 GA counties initially (~500K voters), statewide-ready
data model (159 counties, ~7M voters)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Evidence |
|---|-----------|--------|----------|
| I | Library-First Architecture | PASS | Core features (geocoder, importer, exporter, analyzer, boundary loader) implemented as standalone libraries under `src/voter_api/lib/` with explicit `__init__.py` exports. Each library is independently testable and importable. Package distributed via PyPI. |
| II | Code Quality (NON-NEGOTIABLE) | PASS | All functions/classes/modules will have type hints and Google-style docstrings. Ruff check + format enforced pre-commit. Inline comments for non-obvious logic. |
| III | Testing Discipline (NON-NEGOTIABLE) | PASS | pytest with pytest-cov and pytest-asyncio. Tests organized into `tests/unit/`, `tests/integration/`, `tests/contract/`. Coverage threshold 90% enforced in CI. All new code includes tests before merge. |
| IV | Twelve-Factor Configuration | PASS | Pydantic Settings for all config (DB URL, JWT secret, geocoder keys, etc.). All config via environment variables. `.env.example` documents all required vars. No hardcoded secrets. |
| V | Developer Experience | PASS | `uv` for all Python operations. Typer CLI for imports, geocoding, analysis, exports, migrations, dev server. Docker + docker-compose for full stack. Also runs locally with `uv run` against a local/remote PostgreSQL. ≤3 commands from clone to running. |
| VI | API Documentation | PASS | FastAPI auto-generates OpenAPI/Swagger from Pydantic schemas. `/docs` and `/redoc` available in dev/staging. API versioning via URL prefix (`/api/v1/`). |
| VII | Security by Design | PASS | Pydantic validation at all boundaries. JWT auth on all endpoints. Role-based access (admin/analyst/viewer). SQLAlchemy ORM only (no raw SQL). CORS, rate limiting, request size limits, security headers configured. Dependency scanning in CI. |
| VIII | CI/CD & Version Control | PASS | GitHub Actions on push/PR: ruff check, type check, pytest, coverage. Conventional Commits enforced. Merges to main require passing CI + review. Semantic versioning from commit history. |

**Gate Result**: ALL PASS — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-voter-data-management/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (OpenAPI specs)
│   └── openapi.yaml     # Full OpenAPI 3.1 specification
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/voter_api/
├── __init__.py
├── main.py                  # FastAPI app factory
├── core/
│   ├── __init__.py
│   ├── config.py            # Pydantic Settings
│   ├── database.py          # Async engine, session factory
│   ├── security.py          # JWT encode/decode, password hashing
│   ├── dependencies.py      # FastAPI dependency injection
│   └── logging.py           # Loguru configuration
├── models/
│   ├── __init__.py
│   ├── base.py              # Declarative base, common mixins
│   ├── voter.py             # Voter model
│   ├── geocoded_location.py # GeocodedLocation model
│   ├── geocoder_cache.py    # GeocoderCache model
│   ├── boundary.py          # Boundary model (PostGIS geometry)
│   ├── user.py              # User model
│   ├── audit_log.py         # AuditLog model
│   ├── import_job.py        # ImportJob model
│   ├── export_job.py        # ExportJob model
│   ├── analysis_run.py      # AnalysisRun model
│   └── analysis_result.py   # AnalysisResult model
├── schemas/
│   ├── __init__.py
│   ├── voter.py             # Voter request/response schemas
│   ├── geocoding.py         # Geocoding schemas
│   ├── boundary.py          # Boundary schemas
│   ├── analysis.py          # Analysis schemas
│   ├── auth.py              # Auth request/response schemas
│   ├── export.py            # Export schemas
│   └── common.py            # Pagination, error, shared schemas
├── api/
│   ├── __init__.py
│   ├── router.py            # Root API router
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── voters.py        # Voter CRUD + search endpoints
│   │   ├── geocoding.py     # Geocoding trigger/status endpoints
│   │   ├── boundaries.py    # Boundary import/query endpoints
│   │   ├── analysis.py      # Analysis run/results endpoints
│   │   ├── exports.py       # Export trigger/download endpoints
│   │   ├── imports.py       # Import trigger/status endpoints
│   │   └── auth.py          # Login/token/user management
│   └── middleware.py        # CORS, rate limiting, security headers
├── services/
│   ├── __init__.py
│   ├── voter_service.py     # Voter CRUD, search logic
│   ├── geocoding_service.py # Geocoding orchestration
│   ├── boundary_service.py  # Boundary operations
│   ├── analysis_service.py  # Location analysis orchestration
│   ├── import_service.py    # Import orchestration
│   ├── export_service.py    # Export orchestration
│   ├── auth_service.py      # Auth + user management
│   └── audit_service.py     # Audit log recording
├── lib/
│   ├── __init__.py
│   ├── geocoder/
│   │   ├── __init__.py      # Public API: geocode, batch_geocode
│   │   ├── base.py          # Abstract geocoder provider interface
│   │   ├── census.py        # US Census Bureau provider
│   │   ├── cache.py         # Per-provider caching layer
│   │   └── address.py       # Address reconstruction + normalization
│   ├── importer/
│   │   ├── __init__.py      # Public API: import_voter_file
│   │   ├── parser.py        # CSV/delimiter detection + parsing
│   │   ├── validator.py     # Record validation rules
│   │   └── differ.py        # Import diff generation
│   ├── exporter/
│   │   ├── __init__.py      # Public API: export_voters
│   │   ├── csv_writer.py    # CSV export
│   │   ├── json_writer.py   # JSON export
│   │   └── geojson_writer.py # GeoJSON export
│   ├── analyzer/
│   │   ├── __init__.py      # Public API: run_analysis
│   │   ├── spatial.py       # Point-in-polygon + boundary matching
│   │   └── comparator.py    # Registration vs physical comparison
│   └── boundary_loader/
│       ├── __init__.py      # Public API: load_boundaries
│       ├── shapefile.py     # Shapefile reader
│       └── geojson.py       # GeoJSON reader
└── cli/
    ├── __init__.py
    ├── app.py               # Typer app root
    ├── import_cmd.py        # Import commands
    ├── geocode_cmd.py       # Geocoding commands
    ├── analyze_cmd.py       # Analysis commands
    ├── export_cmd.py        # Export commands
    ├── user_cmd.py          # User management commands
    └── db_cmd.py            # Database migration commands

tests/
├── conftest.py              # Shared fixtures (async DB, test client)
├── unit/
│   ├── lib/
│   │   ├── test_geocoder/
│   │   ├── test_importer/
│   │   ├── test_exporter/
│   │   ├── test_analyzer/
│   │   └── test_boundary_loader/
│   ├── test_schemas/
│   └── test_services/
├── integration/
│   ├── test_api/
│   ├── test_database/
│   └── test_cli/
└── contract/
    └── test_openapi/

alembic/
├── env.py
├── versions/
└── alembic.ini

docker-compose.yml           # PostGIS + API services
Dockerfile                   # Multi-stage Python build
pyproject.toml               # uv/pip project config
.env.example                 # Environment variable documentation
```

**Structure Decision**: Single project structure selected. This is an API-only
service with no frontend. The `src/voter_api/lib/` directory houses all
standalone libraries (geocoder, importer, exporter, analyzer, boundary_loader)
per the Library-First Architecture principle. Each library has an explicit
public API via `__init__.py` and can be tested independently. The `services/`
layer orchestrates libraries with database access. The `api/` layer handles
HTTP concerns. The `cli/` layer provides Typer commands that call services.

## Complexity Tracking

> No constitution violations detected — no entries required.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
