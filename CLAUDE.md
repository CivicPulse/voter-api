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

# E2E tests (requires a running PostGIS database + env vars set)
uv run pytest tests/e2e/ -v

# E2E: collect tests without running (syntax/import check)
uv run pytest tests/e2e/ --collect-only
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
├── unit/           # Library and schema tests (no PostGIS, in-memory SQLite)
├── integration/    # API, database, and CLI tests (in-memory SQLite + mocks for isolation)
├── contract/       # OpenAPI contract tests
└── e2e/            # End-to-end smoke tests (real PostGIS, Alembic migrations)
```

### E2E Tests

The `tests/e2e/` suite runs **61 smoke tests** against a real PostgreSQL/PostGIS database with all Alembic migrations applied. Unlike unit/integration tests (which use in-memory SQLite and mocks), E2E tests exercise the full stack: real app factory, real database, real auth, real queries.

**CI workflow**: `.github/workflows/e2e.yml` — triggers on PRs to `main`. Spins up a `postgis/postgis:15-3.4` service container, runs `alembic upgrade head`, then `pytest tests/e2e/`.

**Running E2E tests locally** (requires a running PostGIS instance):

```bash
# Start PostGIS via docker-compose
docker compose up -d db

# Apply migrations
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run alembic upgrade head

# Run E2E tests
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  ELECTION_REFRESH_ENABLED=false \
  uv run pytest tests/e2e/ -v
```

#### Key files

| File | Purpose |
|---|---|
| `tests/e2e/conftest.py` | Session-scoped fixtures: app factory, DB seeding, authenticated HTTP clients |
| `tests/e2e/test_smoke.py` | 61 smoke tests organized by API router |
| `.github/workflows/e2e.yml` | GitHub Actions workflow with PostGIS service container |

#### How the fixtures work

- **`app`** (session-scoped) — calls `create_app()` which initialises the async engine via lifespan
- **`seed_database`** (session-scoped, autouse) — inserts baseline test data (3 users, 1 election, 1 boundary with real geometry, 1 elected official) using SQLAlchemy Core with `on_conflict_do_update` for idempotency; cleans up after the session
- **`client`** / **`admin_client`** / **`analyst_client`** / **`viewer_client`** — `httpx.AsyncClient` instances wired to the app via `ASGITransport`; role-specific clients include a pre-set `Authorization: Bearer <jwt>` header
- **Fixed UUIDs** — seeded rows use deterministic UUIDs (`BOUNDARY_ID`, `ELECTION_ID`, `OFFICIAL_ID`, etc.) exported from `conftest.py` so tests can reference them

#### Test coverage by router

| Test class | Router | Tests | What it covers |
|---|---|---|---|
| `TestHealth` | auth | 2 | Health check, /info version endpoint |
| `TestAuth` | auth | 8 | Login, refresh, /me, user CRUD, bad credentials, 401/403 |
| `TestBoundaries` | boundaries | 6 | List, filter, detail, types, point-in-polygon, 404 |
| `TestElections` | elections | 6 | List, detail, create, RBAC, results, 404 |
| `TestElectedOfficials` | elected-officials | 7 | List, detail, by-district, full CRUD lifecycle, sources, 404 |
| `TestVoters` | voters | 3 | Auth required, search, 404 |
| `TestGeocoding` | geocoding | 4 | Public geocode/verify/point-lookup endpoints; cache/stats auth enforcement |
| `TestImports` | imports | 3 | Auth, admin list, viewer 403 |
| `TestExports` | exports | 2 | Auth, admin list |
| `TestAnalysis` | analysis | 3 | Auth, admin list, viewer 403 |
| `TestDatasets` | datasets | 1 | Public listing |
| `TestPagination` | cross-cutting | 4 | Parameterized pagination, invalid page_size 422 |
| `TestRBAC` | cross-cutting | 6 | Admin/analyst/viewer role enforcement |
| `TestVoterHistory` | voter-history | 6 | Auth required, RBAC, participation stats |

#### Updating E2E tests when the API changes

Follow these rules whenever you add, modify, or remove API endpoints:

1. **New endpoint** — Add at least one smoke test to the corresponding `Test<Router>` class in `test_smoke.py`. Cover the happy path (expected status code + key response fields) and auth/RBAC if the endpoint is protected. If it's a new router, add a new test class.

2. **New model/table** — If the new endpoint requires seed data, add an `INSERT` to the `seed_database` fixture in `conftest.py`. Use a fixed UUID constant (add it next to `BOUNDARY_ID`, `ELECTION_ID`, etc.) and `on_conflict_do_update(index_elements=["id"], set_={...})` for idempotency (so reruns overwrite stale rows rather than silently skipping them). Add a matching `DELETE` in the cleanup block at the bottom of the fixture.

3. **Changed request/response schema** — Update any test that asserts on renamed/removed fields or sends a request body with the old shape. Search for the field name in `test_smoke.py`.

4. **Changed auth requirements** — If an endpoint's auth or role requirement changes (e.g., public → admin-only), move the test to use the appropriate client fixture (`client` for public, `admin_client` / `analyst_client` / `viewer_client` for authenticated). Update or add 401/403 assertions.

5. **New Alembic migration** — No test changes needed. The CI workflow runs `alembic upgrade head` before tests, so new migrations are applied automatically.

6. **New boundary type** — If the new type needs E2E coverage, add a seeded boundary row to `seed_database` and a test that queries it.

7. **Removing an endpoint** — Delete the corresponding test(s). If seed data is no longer needed by any test, remove it from `seed_database`.

**Checklist for PR authors:**
- [ ] Every new endpoint has at least one E2E test
- [ ] `uv run pytest tests/e2e/ --collect-only` discovers all new tests
- [ ] Lint passes: `uv run ruff check tests/e2e/ && uv run ruff format --check tests/e2e/`

## Dangerous Commands

> **AI agents must NEVER execute these commands.** They are destructive,
> irreversible, and require human judgment to verify the target database.

- **`voter-api db rebuild`** — Drops the entire database schema (`DROP SCHEMA ... CASCADE`), reruns all migrations, and optionally re-imports all seed data. This is intended for local dev/test resets by a human operator who can visually confirm the target database URL. Two interactive confirmations are required. There is no undo.

## Key Conventions

- **Database inspection via MCP** — A PostgreSQL MCP server (`mcp__postgres__query`) is connected to the dev database. **Always use this MCP tool as the first choice** for inspecting the database (schema, data, table sizes, row counts, etc.) instead of running `psql` or other CLI tools. The tool executes read-only SQL queries and returns JSON results. Use it for ad-hoc queries, debugging data issues, verifying migrations, and exploring table contents.
- **Never use system python** — never invoke `python`, `python3`, `pip`, or `pip3` directly. All Python commands **must** be prefixed with `uv run` (e.g., `uv run pytest`, `uv run python`, `uv run alembic`). Use `uv add <pkg>`, `uv add --dev <pkg>`, `uv remove <pkg>` for package management. Use `uv sync` to install dependencies. No exceptions.
- **Conventional Commits** — all commit messages must follow the spec (see `docs/convential_commits.md`)
- **12-factor config** — all configuration via environment variables, validated by Pydantic Settings; `.env.example` documents all required vars
- **Type hints** on all functions/classes; **Google-style docstrings** on all public APIs
- **Ruff** for both linting and formatting — must pass with zero violations before commit
- **JWT-only auth** with role-based access control (admin/analyst/viewer)
- **No raw SQL in application code** — SQLAlchemy ORM/Core exclusively in `src/`; test seeding/cleanup may use Core constructs
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

## Deployment (Kubernetes / ArgoCD)

**Dev URL**: `https://voteapi-dev.civpulse.org` (namespace: `civpulse-dev`)
**Production URL**: `https://voteapi.civpulse.org` (namespace: `civpulse-prod`)
**Legacy URL**: `https://voteapi.kerryhatcher.com` (still functional via CORS regex)

The app runs on k3s (bare metal) and is deployed via ArgoCD GitOps. Docker images are built and pushed to GHCR; ArgoCD watches the k8s manifests in `k8s/` and syncs changes to the cluster automatically.

### Deploy flow

Deploys are triggered automatically on every merge to `main`:

1. **CI passes** — `.github/workflows/ci.yml` runs tests and lint
2. **Build & push** — `.github/workflows/build-push.yaml` builds the Docker image and pushes to `ghcr.io/civicpulse/voter-api:sha-<SHORT_SHA>`
3. **Manifest update** — The same workflow commits the new image tag back to `k8s/apps/voter-api-dev/deployment.yaml` and `k8s/apps/voter-api-prod/deployment.yaml`
4. **ArgoCD sync** — ArgoCD detects the manifest change and rolls out the new image to both namespaces
5. **Migrations** — An init container (`voter-api db upgrade`) runs Alembic migrations before the main container starts on each rollout

No manual deploy command is needed — merging to `main` is sufficient.

### Kubernetes manifests

Manifests live in `k8s/apps/`:

| Path | Namespace | Purpose |
|---|---|---|
| `k8s/apps/voter-api-dev/` | `civpulse-dev` | Dev environment |
| `k8s/apps/voter-api-prod/` | `civpulse-prod` | Production environment |

Each directory contains `deployment.yaml`, `service.yaml`, `ingress.yaml`, and `voter-api-secret.yaml.example`.

### Secrets

Secrets are managed as a Kubernetes Secret named `voter-api-secret` in each namespace. Use the example file as a template:

```
k8s/apps/voter-api-prod/voter-api-secret.yaml.example
k8s/apps/voter-api-dev/voter-api-secret.yaml.example
```

Apply with `kubectl apply -f` — never commit filled-in secrets to the repo.

### Ingress

Traffic path: **Cloudflare → cloudflared (`civpulse-infra`) → Traefik → voter-api Service**

Defined as a Traefik `IngressRoute` resource in each app's `ingress.yaml`.

### Verification

```bash
uv run voter-api deploy-check --url https://voteapi-dev.civpulse.org  # dev
uv run voter-api deploy-check                                           # prod (default URL)
```

### Troubleshooting

- **View logs**: `kubectl logs -n civpulse-prod deploy/voter-api` (or `civpulse-dev`)
- **Check rollout status**: `kubectl rollout status -n civpulse-prod deploy/voter-api`
- **ArgoCD sync status**: Check ArgoCD UI or `argocd app get voter-api-prod`
- **Migration failures**: `kubectl logs -n civpulse-prod -l app=voter-api -c migrate`
- **Restart the pod**: `kubectl rollout restart -n civpulse-prod deploy/voter-api`

<!-- MANUAL ADDITIONS END -->

## Recent Changes
- 013-batch-boundary-check: Added Python 3.13 + FastAPI, SQLAlchemy 2.x async, GeoAlchemy2, PostGIS `ST_Contains`, Pydantic v2
- 012-election-lifecycle: Added Python 3.13 + FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, GeoAlchemy2
- 011-stale-geocoding-jobs: Added Python 3.13 + FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Loguru

### 009-enhanced-auth

**Enhanced Authentication** — Added four capabilities: (1) self-service password reset via emailed token, (2) admin-initiated user invitations, (3) TOTP two-factor authentication with recovery codes and lockout, (4) passkey (WebAuthn) registration and login as a standalone login alternative.

New libraries: `lib/mailer/` (MailgunMailer + Jinja2 templates), `lib/totp/` (TOTPManager with Fernet encryption), `lib/passkey/` (PasskeyManager wrapping py-webauthn).

New models: `PasswordResetToken`, `UserInvite` (auth_tokens.py), `TOTPCredential`, `TOTPRecoveryCode` (totp.py), `Passkey` (passkey.py). Four new Alembic migrations (025–028).

21 new/modified endpoints. **Breaking change**: POST /auth/login migrated from OAuth2 form-data to JSON body with optional `totp_code` field. Passkey login bypasses TOTP enforcement per spec (Option A).

Key files:

### 008-auto-data-import

**Voter Import Performance** — `import_service.py` was rewritten to use bulk PostgreSQL UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) instead of per-record SELECT+INSERT/UPDATE. Key changes: `_prepare_records_for_db()` handles date/type coercion in a single pass, `_upsert_voter_batch()` executes bulk upserts in sub-batches of 500 rows (staying under asyncpg's 32,767 parameter limit), and `_process_chunk()` encapsulates per-chunk validation and upsert logic. Uses `RETURNING (xmax = 0)::int` to distinguish inserts from updates for accurate job counts. `first_seen_in_import_id` is excluded from the ON CONFLICT update set so it's only set on initial insert.

Key files:


### 005-elected-officials

**Elected Officials API** — Manages canonical elected official records with multi-source data provider support. Two new tables (`elected_officials`, `elected_official_sources`) added in migration 015. Officials are linked to districts via soft join on `(boundary_type, district_identifier)`. Source records from external providers (Open States, Google Civic, etc.) are cached with full provenance. Admin approval workflow supports three states: `auto` (unreviewed), `approved` (admin-verified), `manual` (admin-entered). Nine REST endpoints cover listing, district lookup, source comparison, CRUD, and approval. JSONB `external_ids` column enables flexible cross-referencing across provider ID schemes.

Key files:

### 002-static-dataset-publish

**County Metadata** — Census TIGER/Line attributes are stored in a dedicated `county_metadata` table (migration 011), keyed by FIPS GEOID. Populated automatically during `import all-boundaries` from the same county shapefile. The boundary detail endpoint (`GET /api/v1/boundaries/{id}`) includes a `county_metadata` field when `boundary_type == "county"`, with typed fields like FIPS codes, statistical area codes, land/water area, and computed km² values. Designed as the join point for future Census ACS demographic enrichment.

Key files:


## Active Technologies
- Python 3.13 + FastAPI, SQLAlchemy 2.x async, GeoAlchemy2, PostGIS `ST_Contains`, Pydantic v2 (013-batch-boundary-check)
- PostgreSQL + PostGIS (existing tables only — no migrations) (013-batch-boundary-check)
