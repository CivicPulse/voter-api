# Implementation Plan: Election Result Tracking

**Branch**: `004-election-tracking` | **Date**: 2026-02-14 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-election-tracking/spec.md`

## Summary

Build an election result tracking system that ingests live results from the Georgia Secretary of State JSON data feed, stores statewide and county-level results, and serves them via JSON and GeoJSON API endpoints. Admin users manage elections (create, update, finalize, manual refresh). Active elections auto-refresh on a configurable interval via an asyncio background loop. County results join to existing PostGIS boundary geometries for map visualization. Results are cached at the CDN edge with status-dependent TTLs (60s active, 24h finalized).

## Technical Context

**Language/Version**: Python 3.13 (see `.python-version`)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, httpx, Alembic, Typer, Loguru
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing `boundaries`, `county_metadata` tables; new `elections`, `election_results`, `election_county_results` tables)
**Testing**: pytest with pytest-asyncio, pytest-cov (90% coverage threshold)
**Target Platform**: Linux server (piku deployment behind Cloudflare Tunnel)
**Project Type**: Single project (API + CLI)
**Performance Goals**: <2s response time for results (SC-001); support 10+ concurrent active elections (SC-004)
**Constraints**: No new dependencies beyond what's already in pyproject.toml; piku single-worker deployment model (no Celery/Redis)
**Scale/Scope**: ~160 counties per election, ~10 concurrent elections max, single ballot item per election feed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First Architecture | PASS | New `lib/election_tracker/` library with SoS feed parser, result ingester, and data validator as standalone units |
| II. Code Quality (NON-NEGOTIABLE) | PASS | Type hints, Google-style docstrings, ruff check/format required |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for parser/validator, integration tests for API/CLI, contract tests for OpenAPI |
| IV. Twelve-Factor Configuration | PASS | New env vars `ELECTION_REFRESH_ENABLED`, `ELECTION_REFRESH_INTERVAL` via Pydantic Settings |
| V. Developer Experience | PASS | CLI command `voter-api election refresh` for manual use; `uv run` for all operations |
| VI. API Documentation | PASS | OpenAPI spec in `contracts/openapi.yaml`; Pydantic schemas auto-generate Swagger docs |
| VII. Security by Design | PASS | Admin endpoints protected by `require_role("admin")`; Pydantic validation on all inputs; no raw SQL |
| VIII. CI/CD & Version Control | PASS | Conventional Commits; feature branch `004-election-tracking`; all quality gates enforced |

**Post-Phase 1 Re-check**: All principles satisfied. No violations.

## Project Structure

### Documentation (this feature)

```text
specs/004-election-tracking/
├── plan.md              # This file
├── research.md          # Phase 0: design decisions and alternatives
├── data-model.md        # Phase 1: database schema design
├── quickstart.md        # Phase 1: setup and usage guide
├── contracts/
│   └── openapi.yaml     # Phase 1: OpenAPI 3.1 specification
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/voter_api/
├── models/
│   └── election.py              # Election, ElectionResult, ElectionCountyResult ORM models
├── schemas/
│   └── election.py              # Pydantic v2 request/response schemas
├── api/v1/
│   └── elections.py             # FastAPI route handlers (7 endpoints)
├── services/
│   └── election_service.py      # Business logic: CRUD, refresh orchestration, GeoJSON generation
├── lib/
│   └── election_tracker/
│       ├── __init__.py           # Public API exports
│       ├── parser.py             # SoS JSON feed parser + Pydantic validation models
│       ├── fetcher.py            # httpx-based SoS feed HTTP client
│       └── ingester.py           # Result upsert logic (statewide + county)
├── cli/
│   └── election_cmd.py          # Typer CLI: refresh command
└── core/
    └── config.py                # Extended with ELECTION_REFRESH_* settings

alembic/versions/
└── 015_election_tracking.py     # Migration: elections, election_results, election_county_results

tests/
├── unit/
│   └── lib/
│       └── test_election_tracker/
│           ├── test_parser.py    # SoS feed parsing and validation
│           ├── test_fetcher.py   # HTTP client (mocked httpx)
│           └── test_ingester.py  # Result upsert logic
├── integration/
│   ├── test_election_api.py     # API endpoint tests (auth, CRUD, results, GeoJSON)
│   └── test_election_cli.py     # CLI refresh command tests
└── contract/
    └── test_election_contract.py # OpenAPI schema compliance tests
```

**Structure Decision**: Single project layout. New code follows existing patterns — models in `models/`, schemas in `schemas/`, routes in `api/v1/`, business logic in `services/`, standalone library in `lib/election_tracker/`. No structural changes to existing code.

## Key Design Decisions

### 1. Hybrid Relational + JSONB Data Model

Three new tables: `elections` (metadata), `election_results` (statewide JSONB), `election_county_results` (per-county JSONB). JSONB stores the full `ballotOptions` array from the SoS feed, preserving structure and fidelity (FR-006) without normalizing into 6+ relational tables. County results are separated for efficient PostGIS GeoJSON joins. See [data-model.md](data-model.md).

### 2. Asyncio Background Refresh (Zero New Dependencies)

An asyncio background task loop runs in the FastAPI lifespan context. It queries active elections, fetches their SoS feeds via httpx, and upserts results. Configurable via `ELECTION_REFRESH_ENABLED` and `ELECTION_REFRESH_INTERVAL` env vars. A CLI command (`voter-api election refresh`) provides manual/cron-triggered refresh. No Celery, APScheduler, or Redis needed. See [research.md](research.md) section 3.

### 3. County Name Matching via county_metadata

SoS feed uses "Houston County" format. Strip " County" suffix and match against `county_metadata.name` (case-insensitive). GeoJSON joins follow the path: `election_county_results` → `county_metadata` (by name) → `boundaries` (by GEOID, boundary_type='county'). See [research.md](research.md) section 2.

### 4. Status-Dependent Cache-Control Headers

Active elections: `Cache-Control: public, max-age=60`. Finalized elections: `Cache-Control: public, max-age=86400`. Set per-response in route handlers based on `election.status`. Cloudflare edge respects these headers. See [research.md](research.md) section 4.

### 5. Library-First: lib/election_tracker/

Three standalone modules:
- **parser.py**: Pydantic models for the SoS JSON structure + parse/validate functions. No DB or HTTP dependencies.
- **fetcher.py**: httpx-based HTTP client. Accepts URL, returns parsed feed or raises typed errors. Follows `CensusGeocoder` pattern.
- **ingester.py**: Accepts parsed feed + SQLAlchemy session, performs upserts. Pure DB logic, no HTTP.

Each module is independently testable with unit tests.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
