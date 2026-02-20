# Implementation Plan: Single-Address Geocoding Endpoint

**Branch**: `003-address-geocoding-endpoint` | **Date**: 2026-02-13 | **Spec**: `specs/003-address-geocoding-endpoint/spec.md`
**Input**: Feature specification from `/specs/003-address-geocoding-endpoint/spec.md`

## Summary

Expose three public GET endpoints under `/api/v1/geocoding/` for on-demand address operations (no authentication required):

1. **`/geocode`** — accepts a freeform street address, returns coordinates + confidence score. Uses existing geocoder provider infrastructure with cache-first strategy.
2. **`/verify`** — accepts a partial/malformed address, returns USPS-normalized form, component validation feedback, and up to 10 autocomplete suggestions from the address store.
3. **`/point-lookup`** — accepts lat/lng coordinates (optional GPS accuracy radius), returns all boundary districts containing that point via PostGIS spatial query.

Key architectural addition: A new canonical `addresses` table serves as the dedicated address store. Geocoder cache and voter records reference it via FK. This ensures address identity persists independently of referencing entities.

## Technical Context

**Language/Version**: Python 3.13 (see `.python-version`)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, httpx, Alembic
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing `geocoder_cache`, `boundaries`, `voters` tables; new `addresses` table)
**Testing**: pytest, pytest-asyncio, pytest-cov (90% threshold)
**Target Platform**: Linux server (piku deployment on `hatchweb`)
**Project Type**: Single (API + CLI)
**Performance Goals**: 5s uncached geocode (SC-001), 500ms cached (SC-002), 500ms verify (SC-005), 1s point-lookup (SC-007)
**Constraints**: 60 req/min global rate limit, Georgia service area only (static bounding box). Geocode/verify/point-lookup are public (no auth); batch/geocode-all are admin-only.
**Scale/Scope**: ~7M voter records, millions of unique addresses, single-server deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First Architecture | PASS | New code in `lib/geocoder/` (verify, point_lookup, address normalization). Each module independently testable with explicit public API via `__init__.py`. |
| II. Code Quality (NON-NEGOTIABLE) | PASS | All new code will have type hints, Google-style docstrings, ruff compliance. |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for libs, integration tests for API endpoints, contract tests against OpenAPI spec. 90% coverage target. |
| IV. Twelve-Factor Configuration | PASS | Georgia bounding box as domain constants (not config — these are invariants). All other config via existing Pydantic Settings. |
| V. Developer Experience | PASS | No new tools. `uv run` for all operations. Migration via existing `voter-api db upgrade`. |
| VI. API Documentation | PASS | OpenAPI auto-generated from FastAPI + Pydantic schemas. Swagger UI + ReDoc available. |
| VII. Security by Design | PASS | JWT auth on all three endpoints. Pydantic validation at boundary. SQLAlchemy ORM only. Existing CORS + rate limiting. |
| VIII. CI/CD & Version Control | PASS | Conventional commits. Feature branch. CI runs linting + tests + coverage. |

**Gate result**: PASS — no violations. Proceeding to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/003-address-geocoding-endpoint/
├── plan.md              # This file
├── research.md          # Phase 0 output — technology decisions
├── data-model.md        # Phase 1 output — database schema with new addresses table
├── quickstart.md        # Phase 1 output — usage guide
├── contracts/
│   └── openapi.yaml     # Phase 1 output — OpenAPI 3.1 spec
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/voter_api/
├── models/
│   ├── address.py              # NEW: Address ORM model (canonical address store)
│   ├── geocoder_cache.py       # MODIFIED: Add address_id FK + relationship
│   └── voter.py                # MODIFIED: Add residence_address_id FK + relationship
├── schemas/
│   └── geocoding.py            # MODIFIED: Add geocode/verify/point-lookup response schemas
├── api/v1/
│   └── geocoding.py            # MODIFIED: Add 3 new GET endpoints
├── services/
│   ├── geocoding_service.py    # MODIFIED: Add single-address geocoding + address upsert
│   └── address_service.py      # NEW: Address entity CRUD + lookup operations
├── lib/
│   └── geocoder/
│       ├── __init__.py          # MODIFIED: Export new public APIs
│       ├── address.py           # MODIFIED: Add normalize_freeform_address(), parse_address_components()
│       ├── verify.py            # NEW: Address verification/validation logic
│       ├── point_lookup.py      # NEW: Georgia bbox validation, meter-to-degree conversion
│       └── census.py            # MODIFIED: Raise GeocodingProviderError on transport errors
└── cli/
    └── (no changes)

tests/
├── unit/
│   └── lib/test_geocoder/
│       ├── test_address.py          # MODIFIED: Tests for freeform normalization + parsing
│       ├── test_verify.py           # NEW: Address verification tests
│       └── test_point_lookup.py     # NEW: Georgia bbox + meter-to-degree tests
├── integration/
│   └── test_api/
│       ├── test_geocode_endpoint.py    # NEW: Geocode endpoint integration tests
│       ├── test_verify_endpoint.py     # NEW: Verify endpoint integration tests
│       └── test_point_lookup_endpoint.py # NEW: Point-lookup endpoint integration tests
└── contract/
    └── test_geocoding_contract.py   # NEW: OpenAPI contract tests
```

**Structure Decision**: Follows existing single-project layout. New code extends existing modules in `lib/geocoder/`, `services/`, `api/v1/`, and `schemas/`. One new model file (`address.py`), one new service file (`address_service.py`), and two new library modules (`verify.py`, `point_lookup.py`). All other changes are extensions to existing files.

## Constitution Re-Check (Post Phase 1 Design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Library-First Architecture | PASS | `verify.py` and `point_lookup.py` are standalone library modules. `address_service.py` orchestrates DB operations. Address model is independently importable. |
| II. Code Quality (NON-NEGOTIABLE) | PASS | All new modules will include type hints and docstrings. Ruff enforced. |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for each new lib module. Integration tests for each endpoint. Contract tests for OpenAPI compliance. |
| IV. Twelve-Factor Configuration | PASS | No new env vars needed. Georgia bbox is a domain constant. |
| V. Developer Experience | PASS | Single `uv run voter-api db upgrade` for migrations. No new tooling. |
| VI. API Documentation | PASS | Three new endpoints documented via FastAPI auto-generation. OpenAPI contract in `contracts/openapi.yaml`. |
| VII. Security by Design | PASS | Public endpoints (geocode, verify, point-lookup) — no auth required. Admin endpoints (batch, geocode-all) behind `Depends(require_role("admin"))`. Input validated by Pydantic. No raw SQL. Rate limited at 60 req/min per IP. |
| VIII. CI/CD & Version Control | PASS | Feature branch workflow. Commits after each task. |

**Gate result**: PASS — no violations.

## Complexity Tracking

No constitution violations to justify. All design decisions follow existing patterns.
