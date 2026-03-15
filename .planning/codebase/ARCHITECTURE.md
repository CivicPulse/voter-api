# Architecture

**Analysis Date:** 2026-03-13

## Pattern Overview

**Overall:** Library-First Layered Architecture with Async Service Orchestration

**Key Characteristics:**
- All domain capabilities are built as standalone, independently testable libraries in `src/voter_api/lib/` before being wired into services and routes
- Two entry points share the same service layer: the FastAPI HTTP API and the Typer CLI
- All I/O (database, external APIs) is async throughout via `asyncio` + SQLAlchemy 2.x `asyncpg`
- Long-running operations (imports, geocoding runs, analysis runs) execute as in-process `asyncio` background tasks tracked in the database via job records
- No raw SQL in application code — SQLAlchemy ORM/Core exclusively in `src/`
- RBAC enforced at the FastAPI dependency layer; field-level access control via a sensitivity tier system
- Background jobs recover automatically on server restart (orphaned jobs marked `failed` in lifespan)

## Layers

**Core (`src/voter_api/core/`):**
- Purpose: Cross-cutting infrastructure used by every other layer
- Location: `src/voter_api/core/`
- Contains: Pydantic Settings (`config.py`), async engine/session factory (`database.py`), JWT/bcrypt security helpers (`security.py`), FastAPI dependency functions (`dependencies.py`), logging setup (`logging.py`), data sensitivity tier system (`sensitivity.py`), in-process background task runner (`background.py`), shared utilities (`utils.py`)
- Depends on: Only stdlib and third-party packages — no internal imports from other layers
- Used by: All other layers

**Libraries (`src/voter_api/lib/`):**
- Purpose: Domain logic implemented as self-contained, independently testable units with explicit public APIs via `__init__.py` + `__all__`
- Location: `src/voter_api/lib/`
- Contains: Pure business logic; no FastAPI/Typer imports; some libs accept `AsyncSession` for caching (e.g., `lib/geocoder/cache.py`)
- Depends on: `core/` only (specifically `Settings` for configuration)
- Used by: `services/` exclusively

**Models (`src/voter_api/models/`):**
- Purpose: SQLAlchemy ORM table definitions; source of truth for the database schema
- Location: `src/voter_api/models/`
- Contains: One file per table/entity; all inherit `Base` from `models/base.py`; common mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`) applied via multiple inheritance
- Depends on: `core/` (`base.py` only)
- Used by: `services/`, and some `lib/` modules that accept sessions for caching

**Schemas (`src/voter_api/schemas/`):**
- Purpose: Pydantic v2 request/response contracts; separate from ORM models
- Location: `src/voter_api/schemas/`
- Contains: Request schemas (validated inputs), response schemas (serialized outputs), shared pagination types in `common.py`; field-level sensitivity metadata via `sensitivity_tier()` for RBAC filtering at response time
- Depends on: `core/sensitivity.py` for field tagging
- Used by: `api/v1/` route handlers

**Services (`src/voter_api/services/`):**
- Purpose: Business logic orchestration — combine library calls, database queries, and job tracking
- Location: `src/voter_api/services/`
- Contains: One module per domain area; async functions accept `AsyncSession` as first argument; no HTTP/CLI concerns
- Depends on: `lib/`, `models/`, `core/`, `schemas/` (for return types)
- Used by: `api/v1/` route handlers and `cli/` commands

**API Routes (`src/voter_api/api/v1/`):**
- Purpose: HTTP concerns only — path parameters, query params, request bodies, response serialization, auth dependencies
- Location: `src/voter_api/api/v1/`
- Contains: One file per router (named `<domain>_router` or `router`); routes delegate immediately to service functions
- Depends on: `services/`, `schemas/`, `core/dependencies.py`
- Used by: `api/router.py` which mounts all 19 routers under `/api/v1`

**CLI (`src/voter_api/cli/`):**
- Purpose: Typer command groups for admin/operational tasks; shares services with the API
- Location: `src/voter_api/cli/`
- Contains: One file per command group (`<domain>_cmd.py`); `app.py` is the root Typer app with the `serve` command
- Depends on: `services/`, `core/`
- Used by: The `voter-api` console script entrypoint defined in `pyproject.toml`

## Data Flow

**API Request (authenticated endpoint):**

1. HTTP request arrives; middleware stack executes (`RateLimitMiddleware` → `SecurityHeadersMiddleware` → `CORSMiddleware`)
2. FastAPI routes to the matching path operation in `api/v1/<domain>.py`
3. `Depends(get_async_session)` yields a per-request `AsyncSession` from the global session factory
4. `Depends(get_current_user)` decodes JWT, loads `User` from DB; `Depends(require_role(...))` enforces RBAC
5. Route handler calls service functions passing the session
6. Service calls library functions in `lib/` for domain logic; queries/writes via SQLAlchemy ORM
7. Service returns a domain object or dict; route serializes via Pydantic schema response model
8. For `viewer` role, `filter_by_sensitivity()` strips `SYSTEM_GENERATED` fields before returning

**Background Job (import, geocoding, analysis):**

1. API route creates a job record in the DB (e.g., `ImportJob`, `GeocodingJob`, `AnalysisRun`) with `status="pending"`
2. Route calls `task_runner.submit_task(coro)` (from `core/background.py`) and returns immediately with the job ID
3. `InProcessTaskRunner` runs up to 2 concurrent tasks via `asyncio.Semaphore(2)` + `asyncio.create_task()`
4. Background coroutine calls service functions; updates job record status `pending` → `running` → `completed`/`failed`
5. On server restart, `main.py` lifespan function recovers orphaned `running`/`pending` jobs to `failed` status

**Election Auto-Refresh (background loop):**

1. `create_app()` lifespan starts `election_refresh_loop()` from `services/election_service.py` as an `asyncio.create_task()`
2. Loop runs on configurable interval (`ELECTION_REFRESH_INTERVAL` env var, default 60 seconds)
3. Fetches updated results from configured election data source URLs
4. Only allowed domains (configurable via `ELECTION_ALLOWED_DOMAINS`) may be fetched
5. Cancelled cleanly during lifespan shutdown

**CLI Command:**

1. `voter-api <command> [args]` invoked
2. Typer parses args; `app.py` callback initializes logging via `core/logging.py`
3. Command function calls `init_engine()` directly (no lifespan), then calls service functions
4. Service functions execute identically to API path

**State Management:**
- No in-memory application state beyond the engine/session factory singletons and the in-process task runner dict
- All persistent state lives in PostgreSQL; job records are the single source of truth for background task state
- Geocoding results cached in `GeocoderCache` table; keyed by (address_text, provider)

## Key Abstractions

**`BaseGeocoder` (abstract provider interface):**
- Purpose: Pluggable geocoding backend — each provider implements `geocode(address)` and exposes metadata
- Examples: `src/voter_api/lib/geocoder/base.py`, `src/voter_api/lib/geocoder/census.py`, `src/voter_api/lib/geocoder/photon.py`
- Pattern: Provider registry dict in `lib/geocoder/__init__.py`; `get_geocoder(name)` factory; `get_configured_providers(settings)` returns ordered fallback list; providers in fallback order: census → nominatim → geocodio → mapbox → google → photon

**`Base` + Mixins (ORM model base):**
- Purpose: All ORM models inherit from `Base` (declarative) plus `UUIDMixin` (UUID PK), `TimestampMixin` (`created_at`/`updated_at`), and optionally `SoftDeleteMixin` (`deleted_at`)
- Examples: `src/voter_api/models/base.py`
- Pattern: `class Voter(Base, UUIDMixin, TimestampMixin):`

**`Settings` (Pydantic BaseSettings):**
- Purpose: All configuration from environment variables; validated at startup; single source of truth
- Location: `src/voter_api/core/config.py`
- Pattern: `get_settings()` factory called via `Depends(get_settings)` in routes or directly in CLI/lifespan; `.env` file supported; env vars take priority

**Dependency injection chain:**
- Purpose: FastAPI `Depends()` wires `AsyncSession`, `User`, role enforcement, and `Settings` into route handlers without singletons
- Location: `src/voter_api/core/dependencies.py`
- Pattern: `get_async_session` → per-request session; `get_current_user` → JWT decode + DB lookup; `require_role(*roles)` → factory returning a dependency that chains on `get_current_user`

**`BackgroundTaskRunner` (Protocol):**
- Purpose: Abstraction for submitting async background tasks; current impl uses `asyncio.create_task`; Protocol-based for future swap to Celery/ARQ without service layer changes
- Location: `src/voter_api/core/background.py` — `task_runner` singleton (`InProcessTaskRunner`)
- Pattern: `task_runner.submit_task(coroutine)` returns a job ID string; max 2 concurrent tasks via semaphore

**Sensitivity tiers:**
- Purpose: Field-level access control — `GOVERNMENT_SOURCED` vs `SYSTEM_GENERATED`; viewers see only government-sourced fields
- Location: `src/voter_api/core/sensitivity.py`, `src/voter_api/core/dependencies.py` (`filter_by_sensitivity`)
- Pattern: Pydantic fields tagged with `json_schema_extra=sensitivity_tier(SensitivityTier.SYSTEM_GENERATED)`; `filter_by_sensitivity(data, user_role, schema_class)` strips restricted fields for `viewer` role at response time

## Entry Points

**HTTP API (`src/voter_api/main.py` + `src/voter_api/api/router.py`):**
- Location: `src/voter_api/main.py`
- Triggers: `uvicorn voter_api.main:create_app --factory` (production via Procfile; dev via `voter-api serve`)
- Responsibilities: App factory pattern — `create_app()` constructs `FastAPI`, registers middleware (CORS, SecurityHeaders, RateLimit), mounts all 19 routers under `/api/v1` via `api/router.py`; `lifespan()` context manager handles engine init, stale job recovery, and background task teardown
- Global exception handlers: `ValueError` → 400 JSON

**CLI (`src/voter_api/cli/app.py`):**
- Location: `src/voter_api/cli/app.py`
- Triggers: `voter-api <command>` console script defined in `pyproject.toml`
- Responsibilities: Root Typer app with 11 sub-app groups registered in `_register_subcommands()`: db, user, import, geocode, analyze, export, publish, election, meetings, officials, deploy-check, seed

## Error Handling

**Strategy:** Raise typed exceptions in services/libraries; translate to HTTP status codes in route handlers

**Patterns:**
- `ValueError` → 400 (registered as global exception handler in `create_app()`)
- `HTTPException` raised directly in route handlers for 401/403/404
- Service functions raise `ValueError` for invalid inputs; `HTTPException` for not-found resources
- Background jobs catch all exceptions, mark job as `failed`, append to JSONB `error_log`, log via Loguru, and re-raise
- Library functions raise specific typed exceptions: `GeocodingProviderError`, `OutOfBoundsError`, `VoterNotFoundError`, `MailDeliveryError`
- Auth: `MFARequiredException`, `TOTPLockedException` raised by `auth_service`, caught and mapped to structured JSON error responses (`MFARequiredError`, `TOTPLockedError` schemas) in `api/v1/auth.py`
- Pydantic validation errors → 422 (FastAPI default)

## Cross-Cutting Concerns

**Logging:** Loguru throughout — `from loguru import logger`; configured in `core/logging.py` via `setup_logging(log_level, log_dir)`; log level and optional file rotation set via `LOG_LEVEL`/`LOG_DIR` env vars; structured messages use `logger.info("message {}", value)` format (not f-strings)

**Validation:** Pydantic v2 at schema layer (request bodies, response models, settings); SQLAlchemy column constraints at DB layer; service-level guard clauses raise `ValueError`; library-level validators (e.g., `importer.validate_record()`, `geocoder.validate_address_components()`)

**Authentication:** JWT bearer tokens (`Authorization: Bearer <token>`); `oauth2_scheme` in `core/dependencies.py`; access tokens (HS256, 30 min default) + refresh tokens (7 days default); optional TOTP (Fernet-encrypted secrets) + recovery codes; passkey/WebAuthn as standalone login alternative; `require_role()` dependency factory for RBAC with three roles: `admin`, `analyst`, `viewer`

**CORS:** `CORSMiddleware` configured from `CORS_ORIGINS` (comma-separated list) and/or `CORS_ORIGIN_REGEX` env vars; credentials allowed; no default origins — must be explicitly configured

**Rate Limiting:** In-memory sliding window via `RateLimitMiddleware`; 200 req/min per IP default (`RATE_LIMIT_PER_MINUTE`); reads real IP from `CF-Connecting-IP` / `X-Forwarded-For` / `X-Real-IP` headers in priority order

**Database Schema Isolation:** Optional `DATABASE_SCHEMA` env var sets PostgreSQL `search_path` via `connect_args["options"] = "-c search_path={schema},public"` — used for isolated PR preview environments

---

*Architecture analysis: 2026-03-13*
