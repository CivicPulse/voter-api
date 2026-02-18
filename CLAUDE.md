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
- **`ENV`** — piku/nginx settings and non-secret environment variables; committed to the repo. Contains **dev defaults** (hostname, DEBUG logging, etc.). Production overrides are set via `piku config:set` on the server (see Secrets below).

### Secrets

Set secrets on the server via `piku config:set` — never commit them in `ENV`.

**Dev app:**
```bash
ssh piku@hatchweb.tailb56d83.ts.net -- config:set voter-api-dev \
  DATABASE_URL=postgresql+asyncpg://... \
  JWT_SECRET_KEY=... \
  UV_PYTHON_DOWNLOADS=auto
```

**Prod app** (secrets + ENV overrides so dev defaults don't leak):
```bash
ssh piku@hatchweb.tailb56d83.ts.net -- config:set voter-api \
  DATABASE_URL=postgresql+asyncpg://... \
  JWT_SECRET_KEY=... \
  UV_PYTHON_DOWNLOADS=auto \
  NGINX_SERVER_NAME=voteapi.civpulse.org \
  LOG_LEVEL=INFO \
  CORS_ORIGIN_REGEX='^(?:https://(?:(?:.*\.)?voter-web\.pages\.dev|(?:.*\.)?civpulse\.org|(?:.*\.)?kerryhatcher\.com)|http://localhost(?::\d+)?)$'
```

`config:set` values override anything in the `ENV` file, so the committed dev defaults are harmless in prod.

### Ingress: Cloudflare Tunnel

External traffic reaches the app via a Cloudflare Tunnel (`hatchweb`), not direct port exposure:

- **Domains**: `voteapi-dev.hatchtech.dev` (dev), `voteapi.civpulse.org` (prod), `voteapi.kerryhatcher.com` (legacy) — all DNS managed by Cloudflare
- **Tunnel route**: `HTTP://localhost:80` (Cloudflare terminates TLS at the edge)
- Let's Encrypt certs are issued via ACME HTTP-01 through the tunnel. Piku also generates SSL listeners on port 443 — if another site on the server defines conflicting SSL protocol options (e.g. `ssl` vs `ssl http2`), piku's nginx config test will fail and delete the config. The hatchertechnology.com site was disabled to resolve this

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
- 006-voter-history: Added Python 3.13 (see `.python-version`) + FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, Pandas, Typer, Loguru, Alembic
- 005-elected-officials: Added `ElectedOfficial` and `ElectedOfficialSource` models (migration 015), 9 API endpoints under `/api/v1/elected-officials`, admin approval workflow (auto/approved/manual), multi-source data provider architecture
- 004-election-tracking: Added Python 3.13 (see `.python-version`) + FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, httpx, Alembic, Typer, Loguru

### 005-elected-officials

**Elected Officials API** — Manages canonical elected official records with multi-source data provider support. Two new tables (`elected_officials`, `elected_official_sources`) added in migration 015. Officials are linked to districts via soft join on `(boundary_type, district_identifier)`. Source records from external providers (Open States, Google Civic, etc.) are cached with full provenance. Admin approval workflow supports three states: `auto` (unreviewed), `approved` (admin-verified), `manual` (admin-entered). Nine REST endpoints cover listing, district lookup, source comparison, CRUD, and approval. JSONB `external_ids` column enables flexible cross-referencing across provider ID schemes.

Key files:

### 002-static-dataset-publish

**County Metadata** — Census TIGER/Line attributes are stored in a dedicated `county_metadata` table (migration 011), keyed by FIPS GEOID. Populated automatically during `import all-boundaries` from the same county shapefile. The boundary detail endpoint (`GET /api/v1/boundaries/{id}`) includes a `county_metadata` field when `boundary_type == "county"`, with typed fields like FIPS codes, statistical area codes, land/water area, and computed km² values. Designed as the join point for future Census ACS demographic enrichment.

Key files:


## Active Technologies
- Python 3.13 (see `.python-version`) + FastAPI, SQLAlchemy 2.x (async) + GeoAlchemy2, Pydantic v2, Pandas, Typer, Loguru, Alembic (006-voter-history)
- PostgreSQL 15+ / PostGIS 3.x (existing `voters`, `elections`, `import_jobs` tables; new `voter_history` table) (006-voter-history)
