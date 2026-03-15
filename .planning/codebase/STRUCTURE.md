# Codebase Structure

**Analysis Date:** 2026-03-13

## Directory Layout

```
voter-api/
├── src/voter_api/              # Main application package
│   ├── __init__.py             # Package init, version string
│   ├── main.py                 # FastAPI app factory + lifespan manager
│   ├── core/                   # Cross-cutting infrastructure
│   │   ├── config.py           # Pydantic Settings (all env vars)
│   │   ├── database.py         # Async engine + session factory singletons
│   │   ├── security.py         # JWT creation/decode, bcrypt, passkey challenge tokens
│   │   ├── dependencies.py     # FastAPI DI: get_async_session, get_current_user, require_role
│   │   ├── logging.py          # Loguru setup
│   │   ├── background.py       # InProcessTaskRunner (asyncio.create_task + semaphore)
│   │   ├── sensitivity.py      # SensitivityTier enum + sensitivity_tier() field marker
│   │   └── utils.py            # Misc shared utilities
│   ├── models/                 # SQLAlchemy ORM models (one file per entity)
│   │   ├── base.py             # Base, UUIDMixin, TimestampMixin, SoftDeleteMixin
│   │   ├── voter.py            # Voter (central entity, ~60 columns)
│   │   ├── boundary.py         # Boundary with PostGIS geometry (MULTIPOLYGON)
│   │   ├── geocoded_location.py # Geocoding result per voter + provider
│   │   ├── geocoder_cache.py   # Geocoding result cache (keyed by address + provider)
│   │   ├── geocoding_job.py    # Async geocoding job with JSONB error_log
│   │   ├── import_job.py       # Voter file import job with status + diff
│   │   ├── analysis_run.py     # Boundary analysis run record
│   │   ├── analysis_result.py  # Individual boundary mismatch result
│   │   ├── export_job.py       # Export job with format + file path
│   │   ├── user.py             # User account (roles: admin/analyst/viewer)
│   │   ├── auth_tokens.py      # PasswordResetToken, UserInvite
│   │   ├── totp.py             # TOTPCredential, TOTPRecoveryCode
│   │   ├── passkey.py          # WebAuthn passkey credential
│   │   ├── audit_log.py        # Action audit trail
│   │   ├── election.py         # Election, ElectionResult, ElectionCountyResult
│   │   ├── election_event.py   # Election lifecycle event
│   │   ├── candidate.py        # Candidate, CandidateLink
│   │   ├── elected_official.py # ElectedOfficial + sources (multi-provider)
│   │   ├── voter_history.py    # Vote participation history
│   │   ├── county_metadata.py  # Census TIGER/Line attributes (per county)
│   │   ├── county_district.py  # County-to-district mapping
│   │   ├── precinct_metadata.py # Precinct attributes
│   │   ├── precinct_crosswalk.py # Precinct identifier crosswalk
│   │   ├── governing_body.py   # Governing body (city council, board, etc.)
│   │   ├── governing_body_type.py # Governing body type reference
│   │   ├── meeting.py          # Civic meeting record
│   │   ├── agenda_item.py      # Meeting agenda item
│   │   ├── meeting_attachment.py # Meeting file attachment
│   │   ├── meeting_video_embed.py # Meeting video embed
│   │   ├── absentee_ballot.py  # Absentee ballot application
│   │   ├── address.py          # Normalized address record
│   │   └── __init__.py         # Registry — imports all models for Alembic autogenerate
│   ├── schemas/                # Pydantic v2 request/response DTOs
│   │   ├── common.py           # PaginationParams, PaginationMeta, ErrorResponse
│   │   ├── auth.py             # LoginRequest, TokenResponse, UserResponse, TOTP/Passkey schemas
│   │   ├── voter.py            # VoterSummaryResponse, VoterDetailResponse, BatchBoundaryCheckResponse
│   │   ├── boundary.py         # BoundaryResponse (with GeoJSON geometry)
│   │   ├── imports.py          # ImportJobResponse, ImportDiffResponse
│   │   ├── geocoding.py        # GeocodingJobResponse, GeocodedLocationResponse
│   │   ├── analysis.py         # AnalysisRunResponse, AnalysisResultResponse
│   │   ├── export.py           # ExportJobResponse
│   │   ├── election.py         # ElectionResponse, ElectionResultResponse
│   │   ├── elected_official.py # ElectedOfficialResponse, source schemas
│   │   ├── candidate.py        # CandidateResponse
│   │   ├── voter_history.py    # VoterHistoryResponse, participation schemas
│   │   ├── county_metadata.py  # CountyMetadataResponse
│   │   ├── precinct_metadata.py # PrecinctMetadataResponse
│   │   ├── governing_body.py   # GoverningBodyResponse
│   │   ├── governing_body_type.py # GoverningBodyTypeResponse
│   │   ├── meeting.py          # MeetingResponse
│   │   ├── meeting_attachment.py # MeetingAttachmentResponse
│   │   ├── meeting_video_embed.py # MeetingVideoEmbedResponse
│   │   ├── meeting_search.py   # Meeting search schemas
│   │   ├── agenda_item.py      # AgendaItemResponse
│   │   ├── absentee.py         # AbsenteeBallotResponse
│   │   ├── publish.py          # PublishResponse (dataset publishing)
│   │   ├── voter_stats.py      # VoterStatsResponse
│   │   └── __init__.py
│   ├── api/                    # HTTP layer
│   │   ├── router.py           # create_router() mounts all 19 sub-routers; setup_middleware()
│   │   ├── middleware.py       # CORSMiddleware setup, SecurityHeadersMiddleware, RateLimitMiddleware
│   │   └── v1/                 # Versioned endpoints (all under /api/v1)
│   │       ├── auth.py         # /auth/login, /auth/refresh, /auth/me, /users, TOTP, passkeys
│   │       ├── voters.py       # /voters (search), /voters/{id}, district check, locations
│   │       ├── boundaries.py   # /boundaries, /boundaries/{id}, point-in-polygon
│   │       ├── imports.py      # /imports/{type}, /imports/{id}/diff
│   │       ├── geocoding.py    # /geocoding/jobs, /geocoding/verify, /geocoding/point
│   │       ├── analysis.py     # /analysis/runs, /analysis/runs/{id}/results
│   │       ├── exports.py      # /exports, /exports/{id}
│   │       ├── elections.py    # /elections CRUD, /elections/{id}/results
│   │       ├── candidates.py   # /candidates search
│   │       ├── elected_officials.py # /elected-officials CRUD, sources, approval
│   │       ├── voter_history.py # /voter-history, participation stats
│   │       ├── meetings.py     # /meetings CRUD
│   │       ├── agenda_items.py # /agenda-items CRUD
│   │       ├── attachments.py  # /attachments CRUD
│   │       ├── video_embeds.py # /video-embeds CRUD
│   │       ├── absentee.py     # /absentee lookup
│   │       ├── datasets.py     # /datasets (public dataset listing)
│   │       ├── governing_bodies.py # /governing-bodies CRUD
│   │       ├── governing_body_types.py # /governing-body-types reference
│   │       └── __init__.py
│   ├── services/               # Business logic orchestration
│   │   ├── import_service.py   # Bulk voter upsert (500-row batches, index mgmt, autovacuum)
│   │   ├── geocoding_service.py # Provider fallback geocoding, cache, job management
│   │   ├── boundary_service.py # Spatial queries, boundary type enumeration
│   │   ├── voter_service.py    # Voter search (trigram), filter, paginate, district check
│   │   ├── analysis_service.py # Boundary mismatch detection, bulk analysis jobs
│   │   ├── export_service.py   # Export job orchestration (CSV/JSON/GeoJSON)
│   │   ├── auth_service.py     # Login, user CRUD, refresh, password reset, TOTP, passkey
│   │   ├── election_service.py # Election lifecycle + election_refresh_loop() background task
│   │   ├── election_calendar_service.py # Georgia election calendar
│   │   ├── election_resolution_service.py # Election resolution workflow
│   │   ├── candidate_service.py # Candidate queries
│   │   ├── candidate_import_service.py # Candidate data upsert
│   │   ├── results_import_service.py # Election results file import
│   │   ├── elected_official_service.py # Official CRUD, source comparison
│   │   ├── voter_history_service.py # Vote participation tracking + participation summary
│   │   ├── county_metadata_service.py # County metadata queries
│   │   ├── county_district_service.py # County-district mapping
│   │   ├── precinct_metadata_service.py # Precinct metadata
│   │   ├── precinct_crosswalk_service.py # Precinct crosswalk
│   │   ├── governing_body_service.py # Governing body CRUD
│   │   ├── governing_body_type_service.py # Body type reference
│   │   ├── meeting_service.py  # Meeting CRUD
│   │   ├── meeting_search_service.py # Meeting full-text search
│   │   ├── meeting_attachment_service.py # Attachment upload/management
│   │   ├── meeting_video_embed_service.py # Video embed CRUD
│   │   ├── absentee_service.py # Absentee ballot lookup
│   │   ├── address_service.py  # Address normalization
│   │   ├── agenda_item_service.py # Agenda item CRUD
│   │   ├── audit_service.py    # Audit log creation
│   │   ├── voter_stats_service.py # Voter statistics
│   │   ├── publish_service.py  # Dataset publishing to Cloudflare R2
│   │   └── __init__.py
│   ├── lib/                    # Standalone libraries (framework-agnostic, explicitly typed)
│   │   ├── geocoder/           # Pluggable geocoding with provider abstraction + caching
│   │   │   ├── __init__.py     # Public API: get_geocoder(), get_configured_providers(), cache_lookup()
│   │   │   ├── base.py         # BaseGeocoder ABC, GeocodingResult, GeocodeQuality, GeocodeServiceType
│   │   │   ├── census.py       # US Census Bureau geocoder
│   │   │   ├── nominatim.py    # OpenStreetMap Nominatim geocoder
│   │   │   ├── google_maps.py  # Google Maps geocoder
│   │   │   ├── geocodio.py     # Geocodio geocoder
│   │   │   ├── mapbox.py       # Mapbox geocoder
│   │   │   ├── photon.py       # Photon (Komoot) geocoder
│   │   │   ├── address.py      # AddressComponents, reconstruct_address(), normalize_freeform_address()
│   │   │   ├── verify.py       # BaseSuggestionSource, validate_address_components()
│   │   │   ├── cache.py        # cache_lookup(), cache_store() (DB-backed GeocoderCache)
│   │   │   └── point_lookup.py # validate_georgia_coordinates(), OutOfBoundsError
│   │   ├── importer/           # GA SoS voter CSV parsing, validation, diff generation
│   │   │   ├── __init__.py     # Public API: parse_csv_chunks(), validate_batch(), generate_diff()
│   │   │   ├── parser.py       # Chunked CSV reading via Pandas
│   │   │   ├── validator.py    # Per-record field validation
│   │   │   └── differ.py       # detect_field_changes(), generate_diff()
│   │   ├── exporter/           # Multi-format output writers
│   │   │   ├── __init__.py     # Public API
│   │   │   ├── csv_writer.py   # CSV output
│   │   │   ├── json_writer.py  # JSON output
│   │   │   └── geojson_writer.py # GeoJSON output with geometry
│   │   ├── analyzer/           # Spatial analysis, boundary comparison
│   │   │   ├── __init__.py     # Public API: check_batch_boundaries(), find_voter_boundaries()
│   │   │   ├── spatial.py      # PostGIS ST_Contains queries
│   │   │   ├── comparator.py   # compare_boundaries(), extract_registered_boundaries()
│   │   │   └── batch_check.py  # check_batch_boundaries(), BatchBoundaryCheckResult
│   │   ├── boundary_loader/    # Shapefile + GeoJSON ingestion
│   │   │   ├── __init__.py     # Public API: load_boundaries(), BOUNDARY_MANIFEST
│   │   │   ├── shapefile.py    # BoundaryData, read_shapefile()
│   │   │   ├── geojson.py      # read_geojson()
│   │   │   ├── csv_loader.py   # parse_county_districts_csv()
│   │   │   ├── manifest.py     # BOUNDARY_MANIFEST, BoundaryFileEntry, get_manifest()
│   │   │   └── checksum.py     # verify_sha512()
│   │   ├── election_tracker/   # Election state machine
│   │   │   └── __init__.py     # Public API
│   │   ├── election_calendar/  # Georgia election calendar dates
│   │   │   └── __init__.py     # Public API
│   │   ├── candidate_importer/ # Candidate data ingestion
│   │   │   └── __init__.py     # Public API
│   │   ├── results_importer/   # Election results file parsing
│   │   │   └── __init__.py     # Public API
│   │   ├── voter_history/      # Vote participation enrichment
│   │   │   └── __init__.py     # Public API
│   │   ├── absentee/           # Absentee ballot data
│   │   │   └── __init__.py     # Public API
│   │   ├── district_parser/    # District identifier normalization
│   │   │   └── __init__.py     # Public API: pad_district_identifier()
│   │   ├── totp/               # TOTP MFA (Fernet encryption, recovery codes)
│   │   │   ├── __init__.py     # Public API: TOTPManager
│   │   │   └── manager.py
│   │   ├── passkey/            # WebAuthn registration/login (py-webauthn)
│   │   │   ├── __init__.py     # Public API: PasskeyManager
│   │   │   └── manager.py
│   │   ├── mailer/             # Email delivery via Mailgun + Jinja2 templates
│   │   │   ├── __init__.py     # Public API: MailgunMailer, MailDeliveryError
│   │   │   ├── mailer.py       # Mailgun HTTP client
│   │   │   └── templates/      # Jinja2 email templates (.html)
│   │   ├── publisher/          # Cloudflare R2 / S3 object storage
│   │   │   └── __init__.py     # Public API
│   │   ├── meetings/           # Meeting record parsing utilities
│   │   │   └── __init__.py
│   │   ├── officials/          # Elected official data provider abstraction
│   │   │   └── __init__.py     # Public API
│   │   ├── data_loader/        # General data loading utilities
│   │   │   └── __init__.py
│   │   ├── normalize.py        # normalize_registration_number() + other normalizers
│   │   └── election_name_normalizer.py # Election name normalization (AI-assisted)
│   └── cli/                    # Typer CLI commands
│       ├── app.py              # Root app, serve command, _register_subcommands()
│       ├── import_cmd.py       # voter-api import [voters|boundaries|candidates|results|absentee]
│       ├── geocode_cmd.py      # voter-api geocode [batch-job|verify-address]
│       ├── analyze_cmd.py      # voter-api analyze batch-check
│       ├── export_cmd.py       # voter-api export
│       ├── election_cmd.py     # voter-api election [track|resolve]
│       ├── db_cmd.py           # voter-api db [upgrade|downgrade]
│       ├── user_cmd.py         # voter-api user [create|list|update]
│       ├── publish_cmd.py      # voter-api publish (R2 dataset publishing)
│       ├── officials_cmd.py    # voter-api officials [import|...]
│       ├── meetings_cmd.py     # voter-api meetings [...]
│       ├── voter_history_cmd.py # voter-api voter-history [...]
│       ├── deploy_check_cmd.py # voter-api deploy-check --url
│       ├── seed_cmd.py         # voter-api seed (production seed from manifest)
│       ├── seed_dev_cmd.py     # voter-api seed-dev
│       ├── rebuild_cmd.py      # voter-api db rebuild (DANGEROUS — requires 2 confirmations)
│       └── __init__.py
├── tests/
│   ├── unit/                   # No DB; mock external calls; test lib/ and schemas/
│   │   ├── lib/                # One subdirectory per lib module tested
│   │   │   └── test_geocoder/  # e.g., test_cache.py, test_census.py
│   │   └── schemas/            # Schema validation tests
│   ├── integration/            # In-memory SQLite + mocked external APIs
│   │   ├── test_api/           # API endpoint tests (httpx TestClient)
│   │   │   ├── conftest.py     # In-memory DB fixtures, app factory
│   │   │   └── test_*.py       # One file per router
│   │   ├── test_cli/           # CLI command integration tests
│   │   └── test_*.py           # Service integration tests
│   ├── contract/               # OpenAPI contract validation
│   │   └── test_openapi.py
│   ├── e2e/                    # Real PostGIS + Alembic; 61 smoke tests
│   │   ├── conftest.py         # Session-scoped: app, seed_database, auth clients (admin/analyst/viewer)
│   │   └── test_smoke.py       # Test classes organized by router
│   ├── performance/            # Performance benchmarks (optional)
│   └── conftest.py             # Root pytest config
├── alembic/
│   ├── env.py                  # Alembic environment config (imports models/__init__.py for autogenerate)
│   └── versions/               # 51 migration files (numbered, e.g., 001_create_users.py)
├── data/
│   ├── elections/              # Election seed data
│   ├── results/                # Election results data
│   ├── states/                 # State boundary shapefiles
│   └── voter/                  # Voter CSV sample data
├── docs/                       # Developer documentation
│   └── convential_commits.md   # Conventional Commits spec
├── specs/                      # Feature specifications
│   └── 001-voter-data-management/ # OpenAPI contract, data model, task plan
├── k8s/                        # Kubernetes deployment manifests
│   ├── apps/                   # App deployments
│   ├── infra/                  # Infrastructure (ingress, secrets)
│   ├── namespaces/             # Namespace definitions
│   └── postgresql/             # PostgreSQL deployment
├── argocd/                     # ArgoCD GitOps configuration
├── docker/                     # Docker build context files
├── .github/workflows/          # GitHub Actions CI
│   └── e2e.yml                 # E2E tests on PRs to main
├── .planning/codebase/         # GSD codebase analysis documents
├── .specify/                   # Project constitution + templates
├── pyproject.toml              # uv manifest: deps, scripts (voter-api entrypoint), ruff config
├── .python-version             # 3.13
├── .env.example                # All required env vars documented
├── Procfile                    # Piku: release (alembic upgrade head), web (uvicorn --factory)
├── ENV                         # Piku nginx/non-secret config (committed)
├── alembic.ini                 # Alembic CLI config
├── docker-compose.yml          # Local dev: PostGIS + optional services
└── CLAUDE.md                   # AI assistant instructions
```

## Directory Purposes

**`src/voter_api/core/`:**
- Purpose: Application initialization, configuration, database, security — used by every layer
- Key files: `config.py` (all 40+ env vars with validation), `database.py` (engine singleton), `dependencies.py` (DI chain), `background.py` (async task runner)

**`src/voter_api/models/`:**
- Purpose: SQLAlchemy ORM models — one file per table
- All models inherit `Base` + `UUIDMixin` + `TimestampMixin`; `__init__.py` imports all for Alembic autogenerate
- Key files: `base.py` (mixins), `voter.py` (~60 columns, central entity), `boundary.py` (PostGIS geometry)

**`src/voter_api/schemas/`:**
- Purpose: Pydantic v2 request/response DTOs — separate from ORM models
- Pattern: `{Domain}Request` for inputs, `{Domain}Response` for outputs; `common.py` for shared pagination/error types
- Key files: `auth.py`, `voter.py`, `boundary.py`, `imports.py`, `common.py`

**`src/voter_api/api/v1/`:**
- Purpose: HTTP route handlers — thin wrappers around service calls
- Pattern: Each file defines one `APIRouter` instance; router variable named `{domain}_router` or `router`; all auth via `Depends(require_role(...))` or `Depends(get_current_user)`
- Key files: `auth.py`, `voters.py`, `boundaries.py`, `imports.py`

**`src/voter_api/services/`:**
- Purpose: Business logic orchestration — call libs + query DB; accept `AsyncSession` as first param
- Key files: `import_service.py` (bulk upsert), `geocoding_service.py` (provider fallback), `analysis_service.py` (spatial checks), `auth_service.py` (user management)

**`src/voter_api/lib/`:**
- Purpose: Framework-agnostic, independently testable domain libraries
- Pattern: Each lib is a directory with `__init__.py` defining an explicit public API via `__all__`; submodules for implementation details
- Key libs: `geocoder/` (6 providers + cache), `importer/` (CSV parsing), `exporter/` (3 formats), `analyzer/` (spatial), `boundary_loader/` (shapefile ingestion)

**`src/voter_api/cli/`:**
- Purpose: Administrative commands via Typer
- Pattern: Each file creates a `typer.Typer()` app registered in `cli/app.py:_register_subcommands()`
- Key files: `app.py` (root + serve command), `import_cmd.py`, `geocode_cmd.py`

**`tests/unit/`:**
- Purpose: Fast tests with no database or external I/O; test lib/ and schemas/ in isolation
- Run with: `uv run pytest tests/unit/`

**`tests/integration/`:**
- Purpose: API and service tests using in-memory SQLite + mocked external APIs
- Run with: `uv run pytest tests/integration/`

**`tests/e2e/`:**
- Purpose: Full-stack smoke tests against real PostGIS with Alembic migrations applied
- Key files: `conftest.py` (session-scoped fixtures with deterministic UUIDs), `test_smoke.py` (61 tests in `Test{Router}` classes)
- Run with: `uv run pytest tests/e2e/` (requires PostGIS running)

**`alembic/versions/`:**
- Purpose: Database migration history (51 migrations as of analysis date)
- Generated via: `uv run alembic revision --autogenerate -m "description"`
- Applied via: `uv run voter-api db upgrade`

## Key File Locations

**Entry Points:**
- `src/voter_api/main.py` — FastAPI app factory (`create_app()`) called by Uvicorn via `--factory`
- `src/voter_api/cli/app.py` — CLI root Typer app, `serve` command, subcommand registration
- `src/voter_api/__init__.py` — Package version string

**Configuration:**
- `src/voter_api/core/config.py` — All 40+ environment variables with Pydantic validation
- `.env.example` — Template documenting every required env var
- `pyproject.toml` — Dependencies, `voter-api` console script, ruff config
- `.python-version` — Python 3.13

**Database:**
- `src/voter_api/core/database.py` — Engine and session factory singletons (`init_engine`, `get_session_factory`)
- `src/voter_api/models/__init__.py` — Model registry (import all models here for Alembic)
- `alembic/env.py` — Alembic migration environment config
- `alembic/versions/` — Migration files

**Auth and Security:**
- `src/voter_api/core/security.py` — JWT creation/decode, bcrypt, passkey challenge tokens
- `src/voter_api/core/dependencies.py` — `get_async_session`, `get_current_user`, `require_role`, `filter_by_sensitivity`
- `src/voter_api/core/sensitivity.py` — `SensitivityTier` enum, `sensitivity_tier()` field marker

**Middleware:**
- `src/voter_api/api/middleware.py` — `CORSMiddleware` setup, `SecurityHeadersMiddleware`, `RateLimitMiddleware`
- `src/voter_api/api/router.py` — `create_router()` (mounts all sub-routers), `setup_middleware()`

**Testing Fixtures:**
- `tests/e2e/conftest.py` — Session-scoped app, `seed_database` (deterministic UUIDs), auth clients
- `tests/integration/test_api/conftest.py` — In-memory SQLite app + test clients

## Naming Conventions

**Files:**
- Service files: `{domain}_service.py` (e.g., `voter_service.py`, `import_service.py`)
- API route files: `{domain}.py` in `api/v1/` (e.g., `voters.py`, `elections.py`)
- CLI command files: `{command}_cmd.py` (e.g., `import_cmd.py`, `geocode_cmd.py`)
- Library directories: `{concept}/` with `__init__.py` public API (e.g., `geocoder/`, `importer/`)
- Model files: `{entity}.py` singular (e.g., `voter.py`, `boundary.py`)
- Schema files: `{domain}.py` singular matching model name

**Router Variables:**
- Named `{domain}_router` (e.g., `voters_router`, `boundaries_router`) or just `router` for auth

**Functions:**
- Async database I/O: always `async def`
- Queries/fetches: `get_{resource}()`, `search_{resources}()`, `list_{resources}()`
- Creates: `create_{resource}()`
- Updates: `update_{resource}()`
- Private/internal: prefixed with `_` (e.g., `_upsert_voter_batch()`, `_prepare_records_for_db()`)
- Service functions take `session: AsyncSession` as first parameter

**Classes:**
- ORM models: PascalCase matching table name singular (e.g., `Voter`, `Boundary`, `ImportJob`)
- Schemas: `{Domain}Response`, `{Domain}Request`, `{Domain}CreateRequest`
- Exceptions: `{Concept}Error` or `{Concept}Exception`
- Managers (lib): `{Domain}Manager` (e.g., `TOTPManager`, `PasskeyManager`)
- Geocoders: `{Provider}Geocoder` (e.g., `CensusGeocoder`, `NominatimGeocoder`)

## Where to Add New Code

**New API feature (endpoint + service + model):**
1. Model: `src/voter_api/models/{domain}.py` — inherit `Base, UUIDMixin, TimestampMixin`
2. Add to model registry: `src/voter_api/models/__init__.py`
3. Migration: `uv run alembic revision --autogenerate -m "add {domain} table"`
4. Schema: `src/voter_api/schemas/{domain}.py` — `{Domain}Response`, `{Domain}CreateRequest`
5. Service: `src/voter_api/services/{domain}_service.py` — async functions taking `session: AsyncSession`
6. Router: `src/voter_api/api/v1/{domain}.py` — `{domain}_router = APIRouter(prefix="/{domains}", tags=["{domains}"])`
7. Register router: `src/voter_api/api/router.py` — add import + `root_router.include_router({domain}_router)`
8. Tests: `tests/unit/`, `tests/integration/test_api/test_{domain}_api.py`, `tests/e2e/test_smoke.py`

**New library module:**
1. Create `src/voter_api/lib/{concept}/` directory
2. Add `__init__.py` with explicit `__all__` listing the public API
3. Implement submodules for specific concerns (e.g., `base.py`, `{provider}.py`)
4. Unit tests: `tests/unit/lib/test_{concept}/`
5. No direct import of FastAPI/Typer; accept `Settings` or `AsyncSession` only when necessary

**New geocoding provider:**
1. Add `src/voter_api/lib/geocoder/{provider}.py` implementing `BaseGeocoder`
2. Register in `lib/geocoder/__init__.py` `_PROVIDERS` dict
3. Add per-provider config fields to `src/voter_api/core/config.py`
4. Add to `get_configured_providers()` in `lib/geocoder/__init__.py`
5. Unit tests: `tests/unit/lib/test_geocoder/test_{provider}.py`

**New CLI command:**
1. Create `src/voter_api/cli/{command}_cmd.py` with `{command}_app = typer.Typer()`
2. Register in `src/voter_api/cli/app.py:_register_subcommands()`: `app.add_typer({command}_app, name="{command}", help="...")`

**New Alembic migration:**
1. `uv run alembic revision --autogenerate -m "description of change"`
2. Review generated file in `alembic/versions/`
3. Apply: `uv run voter-api db upgrade`

**New E2E test:**
1. Add seed data to `tests/e2e/conftest.py:seed_database` using fixed UUID constants
2. Add test to matching `Test{Router}` class in `tests/e2e/test_smoke.py`
3. Verify: `uv run pytest tests/e2e/ --collect-only`

## Special Directories

**`src/voter_api/lib/mailer/templates/`:**
- Purpose: Jinja2 HTML email templates (password reset, user invite, TOTP recovery codes)
- Generated: No
- Committed: Yes

**`data/`:**
- Purpose: Georgia boundary shapefiles and district data (ZIP archives with SHA512 checksums)
- Generated: No
- Committed: Yes
- Used by: `lib/boundary_loader/` during `voter-api import boundaries`

**`alembic/versions/`:**
- Purpose: Ordered database migration files (51 migrations)
- Generated: Yes (via `alembic revision --autogenerate`)
- Committed: Yes — migrations are code, tracked in git
- Applied automatically by Procfile `release` worker on deploy

**`k8s/` and `argocd/`:**
- Purpose: Kubernetes deployment manifests and ArgoCD GitOps config
- Generated: No
- Committed: Yes

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents consumed by `/gsd:plan-phase` and `/gsd:execute-phase`
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: No (gitignored)

---

*Structure analysis: 2026-03-13*
