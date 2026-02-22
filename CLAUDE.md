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

The `tests/e2e/` suite runs **60 smoke tests** against a real PostgreSQL/PostGIS database with all Alembic migrations applied. Unlike unit/integration tests (which use in-memory SQLite and mocks), E2E tests exercise the full stack: real app factory, real database, real auth, real queries.

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
| `tests/e2e/test_smoke.py` | 60 smoke tests organized by API router |
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
| `TestGeocoding` | geocoding | 3 | Public geocode/verify/point-lookup endpoints (no auth required) |
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

2. **New model/table** — If the new endpoint requires seed data, add an `INSERT` to the `seed_database` fixture in `conftest.py`. Use a fixed UUID constant (add it next to `BOUNDARY_ID`, `ELECTION_ID`, etc.) and `ON CONFLICT DO NOTHING`. Add a matching `DELETE` in the cleanup block at the bottom of the fixture.

3. **Changed request/response schema** — Update any test that asserts on renamed/removed fields or sends a request body with the old shape. Search for the field name in `test_smoke.py`.

4. **Changed auth requirements** — If an endpoint's auth or role requirement changes (e.g., public → admin-only), move the test to use the appropriate client fixture (`client` for public, `admin_client` / `analyst_client` / `viewer_client` for authenticated). Update or add 401/403 assertions.

5. **New Alembic migration** — No test changes needed. The CI workflow runs `alembic upgrade head` before tests, so new migrations are applied automatically.

6. **New boundary type** — If the new type needs E2E coverage, add a seeded boundary row to `seed_database` and a test that queries it.

7. **Removing an endpoint** — Delete the corresponding test(s). If seed data is no longer needed by any test, remove it from `seed_database`.

**Checklist for PR authors:**
- [ ] Every new endpoint has at least one E2E test
- [ ] `uv run pytest tests/e2e/ --collect-only` discovers all new tests
- [ ] Lint passes: `uv run ruff check tests/e2e/ && uv run ruff format --check tests/e2e/`

## Key Conventions

- **Never use system python** — always prefix with `uv run` (e.g., `uv run pytest`, `uv run python`)
- **Package management** — `uv add <pkg>`, `uv add --dev <pkg>`, `uv remove <pkg>`
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

## Deployment (Piku)

**Dev URL**: `https://voteapi-dev.hatchtech.dev` (piku app: `voter-api-dev`)
**Production URL**: `https://voteapi.civpulse.org` (piku app: `voter-api`)
**Legacy URL**: `https://voteapi.kerryhatcher.com` (still functional via CORS regex)

Both environments deploy to the same piku server (`hatchweb`). Three git remotes are configured:

- `origin` — GitHub (`CivicPulse/voter-api`)
- `piku` — dev (`piku@hatchweb.tailb56d83.ts.net:voter-api-dev`)
- `piku-prod` — prod (`piku@hatchweb.tailb56d83.ts.net:voter-api`)

Deploy commands:
```bash
git push piku main          # deploy to dev
git push piku-prod main     # deploy to prod
```

### Configuration files

- **`Procfile`** — defines `release` (Alembic migrations) and `web` (uvicorn ASGI) workers
- **`ENV`** — piku/nginx settings and non-secret environment variables; committed to the repo. Contains **prod defaults** (hostname, logging, etc.). Dev overrides (hostname, log level) and secrets are set via `piku config:set` on the server (see Secrets below).

### Secrets

Set secrets on the server via `piku config:set` — never commit them in `ENV`.

**Dev app** (secrets + ENV overrides for dev hostname and logging):
```bash
ssh piku@hatchweb.tailb56d83.ts.net -- config:set voter-api-dev \
  DATABASE_URL=postgresql+asyncpg://... \
  JWT_SECRET_KEY=... \
  UV_PYTHON_DOWNLOADS=auto \
  NGINX_SERVER_NAME=voteapi-dev.hatchtech.dev \
  LOG_LEVEL=DEBUG
```

**Prod app** (secrets only — ENV file already has prod defaults):
```bash
ssh piku@hatchweb.tailb56d83.ts.net -- config:set voter-api \
  DATABASE_URL=postgresql+asyncpg://... \
  JWT_SECRET_KEY=... \
  UV_PYTHON_DOWNLOADS=auto
```

`config:set` values override anything in the `ENV` file.

### Ingress: Cloudflare Tunnel

External traffic reaches the app via a Cloudflare Tunnel (`hatchweb`), not direct port exposure:

- **Domains**: `voteapi-dev.hatchtech.dev` (dev), `voteapi.civpulse.org` (prod), `voteapi.kerryhatcher.com` (legacy) — all DNS managed by Cloudflare
- **Tunnel route**: `HTTP://localhost:80` (Cloudflare terminates TLS at the edge)
- **SSL disabled on piku**: Cloudflare handles TLS termination, so SSL was removed from piku entirely. Two changes were made on the server:
  1. `acme.sh` renamed to `acme.sh.disabled` (`~/.acme.sh/acme.sh.disabled`) — prevents Let's Encrypt cert issuance
  2. `piku.py` patched to remove SSL listen/cert directives from `NGINX_COMMON_FRAGMENT` — nginx configs only listen on port 80
  - To re-enable SSL: `mv ~/.acme.sh/acme.sh.disabled ~/.acme.sh/acme.sh` and revert the piku.py patch, then redeploy all apps
  - These patches will be lost if piku is updated — re-apply after any `piku update` (same as the uv sync patch)

### Server prerequisites (one-time setup)

These were required on the piku server beyond the standard `piku setup`:

1. **uv**: Must be installed at `~/.local/bin/uv` with PATH including that directory. Without `uv` in PATH, piku falls through to "Generic app" and skips dependency installation.

2. **piku.py patch**: Piku's source hardcodes `--python-preference only-system` in its `uv sync` call (line ~779 of `piku.py`). The server has Python 3.12 but the project requires 3.13. The flag was removed via `sed -i "s/uv sync --python-preference only-system/uv sync/" /home/piku/piku.py` so uv auto-downloads Python 3.13. This patch will be lost if piku is updated — re-apply after any `piku update`.

3. **nginx include**: Piku writes nginx configs to `/home/piku/.piku/nginx/` but the system nginx doesn't include that directory by default. Created `/etc/nginx/sites-enabled/piku.conf` containing:
   ```
   include /home/piku/.piku/nginx/*.conf;
   ```

4. **uwsgi emperor service**: Piku generates uwsgi worker configs in `/home/piku/.piku/uwsgi-enabled/` but the system uwsgi service watches `/etc/uwsgi/apps-enabled/`. Symlinks break on every deploy because piku deletes and recreates the .ini files. Instead, a dedicated systemd service runs uwsgi in emperor mode watching piku's directory:
   ```
   # /etc/systemd/system/piku-uwsgi.service
   [Service]
   User=piku
   Group=www-data
   ExecStart=/usr/bin/uwsgi --emperor /home/piku/.piku/uwsgi-enabled
   Restart=always
   Type=notify
   ```
   This service (`piku-uwsgi`) survives deploys and automatically picks up new piku apps.

5. **nginx path watcher**: Piku writes new nginx configs on each deploy with a fresh port, but doesn't reload nginx. The `piku-nginx.path` systemd unit watches `/home/piku/.piku/nginx/` and triggers `piku-nginx.service` (which runs `systemctl reload nginx`) on changes. Installed from the piku repo's `piku-nginx.{path,service}` files.

### Deploy flow

On `git push piku main` (dev) or `git push piku-prod main` (prod), piku runs:
1. `uv sync` — installs dependencies into `/home/piku/.piku/envs/<app>`
2. Writes new nginx config (with a fresh random port) and uwsgi worker config
3. `release` worker — runs `voter-api db upgrade` (Alembic migrations)
4. `web` worker — spawns `uvicorn --factory voter_api.main:create_app` via uwsgi `attach-daemon`

Piku picks a new random port on each deploy. The `piku-uwsgi` emperor auto-restarts the vassal, and the `piku-nginx.path` systemd path watcher detects config changes and auto-reloads nginx. No manual intervention needed after `git push`.

### Verification

```bash
uv run voter-api deploy-check --url https://voteapi-dev.hatchtech.dev   # dev
uv run voter-api deploy-check                                            # prod (default URL)
```

### Troubleshooting

- **502 Bad Gateway after deploy**: Check `systemctl status piku-nginx.path` (should be `active (waiting)`) and `systemctl status piku-uwsgi` (should be `active (running)`). If either is down, restart it. Also check if uvicorn is running: `ssh piku@... -- ps <app>`
- **"Generic app" on deploy**: `uv` is not in PATH on the server
- **"No interpreter found for Python 3.13"**: The piku.py patch was lost (re-apply after `piku update`)
- **Stale venv errors**: Remove and redeploy: `ssh piku@... -- run <app> -- rm -rf /home/piku/.piku/envs/<app>` then `ssh piku@... -- deploy <app>`
- **View dev logs**: `ssh piku@hatchweb.tailb56d83.ts.net -- logs voter-api-dev`
- **View prod logs**: `ssh piku@hatchweb.tailb56d83.ts.net -- logs voter-api`

<!-- MANUAL ADDITIONS END -->

## Recent Changes
- 008-auto-data-import: Added Python 3.13 + httpx (async HTTP downloads), typer (CLI), loguru (logging), tqdm (progress bars) — all already in pyproject.toml
- 008-auto-data-import: Voter import performance optimization — replaced row-by-row SELECT+INSERT/UPDATE with bulk PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` (via `sqlalchemy.dialects.postgresql.insert`), ~10-20x faster for large imports
- 007-meeting-records: Added Python 3.13+ + FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic, Typer, Loguru, aiofiles (new — async file I/O)
- 006-voter-history: Added Python 3.13 (see `.python-version`) + FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, Pandas, Typer, Loguru, Alembic
- 005-elected-officials: Added `ElectedOfficial` and `ElectedOfficialSource` models (migration 015), 9 API endpoints under `/api/v1/elected-officials`, admin approval workflow (auto/approved/manual), multi-source data provider architecture

### 008-auto-data-import

**Voter Import Performance** — `import_service.py` was rewritten to use bulk PostgreSQL UPSERT (`INSERT ... ON CONFLICT DO UPDATE`) instead of per-record SELECT+INSERT/UPDATE. Key changes: `_prepare_records_for_db()` handles date/type coercion in a single pass, `_upsert_voter_batch()` executes bulk upserts in sub-batches of 500 rows (staying under asyncpg's 32,767 parameter limit), and `_process_chunk()` encapsulates per-chunk validation and upsert logic. Uses `RETURNING (xmax = 0)::int` to distinguish inserts from updates for accurate job counts. `first_seen_in_import_id` is excluded from the ON CONFLICT update set so it's only set on initial insert.

Key files:

- `src/voter_api/services/import_service.py` — bulk upsert logic (`_upsert_voter_batch`, `_prepare_records_for_db`, `_process_chunk`)

### 005-elected-officials

**Elected Officials API** — Manages canonical elected official records with multi-source data provider support. Two new tables (`elected_officials`, `elected_official_sources`) added in migration 015. Officials are linked to districts via soft join on `(boundary_type, district_identifier)`. Source records from external providers (Open States, Google Civic, etc.) are cached with full provenance. Admin approval workflow supports three states: `auto` (unreviewed), `approved` (admin-verified), `manual` (admin-entered). Nine REST endpoints cover listing, district lookup, source comparison, CRUD, and approval. JSONB `external_ids` column enables flexible cross-referencing across provider ID schemes.

Key files:

### 002-static-dataset-publish

**County Metadata** — Census TIGER/Line attributes are stored in a dedicated `county_metadata` table (migration 011), keyed by FIPS GEOID. Populated automatically during `import all-boundaries` from the same county shapefile. The boundary detail endpoint (`GET /api/v1/boundaries/{id}`) includes a `county_metadata` field when `boundary_type == "county"`, with typed fields like FIPS codes, statistical area codes, land/water area, and computed km² values. Designed as the join point for future Census ACS demographic enrichment.

Key files:


## Active Technologies
- Python 3.13+ + FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Alembic, Typer, Loguru, aiofiles (new — async file I/O) (007-meeting-records)
- PostgreSQL 15+ / PostGIS 3.x (existing) + local filesystem for attachments (new) (007-meeting-records)
- Python 3.13 + httpx (async HTTP downloads), typer (CLI), loguru (logging), tqdm (progress bars) — all already in pyproject.toml (008-auto-data-import)
- PostgreSQL + PostGIS (via existing import commands); local filesystem for downloaded data files (008-auto-data-import)
