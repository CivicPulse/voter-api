# Tasks: Voter Data Management

**Input**: Design documents from `/specs/001-voter-data-management/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/openapi.yaml, quickstart.md

**Tests**: Included. The constitution (Principle III) requires 90% test coverage and tests for all new code before merge.

**Organization**: Tasks are grouped by user story (US1–US6) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/voter_api/` for source, `tests/` for tests, `alembic/` for migrations

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — directory structure, dependency management, containerization, CI

- [x] T001 Create full project directory structure with all `__init__.py` files per plan.md (src/voter_api/{core,models,schemas,api/v1,services,lib/{geocoder,importer,exporter,analyzer,boundary_loader},cli}/, tests/{unit/{lib/{test_geocoder,test_importer,test_exporter,test_analyzer,test_boundary_loader},test_schemas,test_services,test_core},integration/{test_api,test_database,test_cli},contract/test_openapi,performance/fixtures}/)
- [x] T002 Configure pyproject.toml with hatchling build system, all runtime dependencies (fastapi, sqlalchemy[asyncio], geoalchemy2, asyncpg, pydantic, pydantic-settings, typer, loguru, pandas, alembic, pyjwt, passlib[bcrypt], httpx, geopandas, pyogrio, shapely, uvicorn), dev dependencies (pytest, pytest-cov, pytest-asyncio, httpx, ruff, mypy, pip-audit), CLI entry point (`voter-api = "voter_api.cli.app:app"`), ruff, mypy, and pytest tool config in pyproject.toml
- [x] T003 [P] Create .env.example documenting all required (DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES, JWT_REFRESH_TOKEN_EXPIRE_DAYS) and optional (GEOCODER_DEFAULT_PROVIDER, GEOCODER_BATCH_SIZE, GEOCODER_RATE_LIMIT_PER_SECOND, IMPORT_BATCH_SIZE, EXPORT_DIR, LOG_LEVEL, CORS_ORIGINS, API_V1_PREFIX) environment variables in .env.example
- [x] T004 [P] Create Dockerfile with multi-stage uv build: builder stage on ghcr.io/astral-sh/uv:python3.13-bookworm-slim with layer-cached dependency install, final stage on python:3.13-slim-bookworm copying only .venv, UV_COMPILE_BYTECODE=1 in Dockerfile
- [x] T005 [P] Create docker-compose.yml with PostGIS 15-3.4 service (pg_isready healthcheck, pgdata volume), API service (depends_on db healthy, env_file, port 8000), and volumes in docker-compose.yml
- [x] T006 [P] Create GitHub Actions CI workflow with ruff check, ruff format --check, mypy type checking, pytest --cov with 90% threshold, and pip-audit dependency vulnerability scanning on push/PR in .github/workflows/ci.yml
- [x] T007 [P] Create .gitignore for Python bytecode, .venv, .env, __pycache__, .pytest_cache, .ruff_cache, *.egg-info, dist/, exports/, .mypy_cache, IDE files in .gitignore

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented — config, database, auth, audit, data sensitivity, rate limiting, API framework, CLI framework, migrations, test fixtures

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T008 Implement Pydantic Settings configuration with all env vars (database, JWT, geocoder, import, export, logging, CORS, API prefix) and validation in src/voter_api/core/config.py
- [x] T009 [P] Configure Loguru structured logging with JSON output, configurable log level, and request context in src/voter_api/core/logging.py
- [x] T010 Create SQLAlchemy declarative base with UUID primary key mixin (default uuid4) and created_at/updated_at timestamp mixin (server_default, onupdate) in src/voter_api/models/base.py
- [x] T011 Implement async engine creation (create_async_engine with asyncpg), async_sessionmaker factory, and engine lifecycle helpers (init/dispose) in src/voter_api/core/database.py
- [x] T012 [P] Implement JWT access/refresh token creation and validation (PyJWT), bcrypt password hashing and verification (passlib), and token payload structure (sub, role, exp) in src/voter_api/core/security.py
- [x] T013 Create User model with id, username (unique), email (unique), hashed_password, role (admin/analyst/viewer), is_active, created_at, last_login_at per data-model.md in src/voter_api/models/user.py
- [x] T014 [P] Create AuditLog model with id, timestamp, user_id (no FK), username, action, resource_type, resource_ids (JSONB), request_ip, request_endpoint, request_metadata (JSONB) per data-model.md in src/voter_api/models/audit_log.py
- [x] T015 [P] Create common Pydantic v2 schemas: PaginationParams (page, page_size with validation), PaginationMeta (total, page, page_size, total_pages), ErrorResponse (detail, code, errors) in src/voter_api/schemas/common.py
- [x] T016 [P] Create auth Pydantic v2 schemas: LoginRequest, RefreshRequest, TokenResponse (access_token, refresh_token, token_type, expires_in), UserCreateRequest (with validation), UserResponse per OpenAPI spec in src/voter_api/schemas/auth.py
- [x] T017 Implement FastAPI dependency injection: get_async_session (yield async session), get_current_user (decode JWT, lookup user), require_role factory (admin/analyst/viewer role checks) in src/voter_api/core/dependencies.py
- [x] T018 Implement auth service: authenticate_user (verify password, update last_login), create_user (hash password, validate uniqueness), list_users (paginated), create_access_token, create_refresh_token, refresh_access_token in src/voter_api/services/auth_service.py
- [x] T019 [P] Implement audit service: log_access (create immutable audit record from request context), query_audit_logs (filter by user, action, resource, timestamp range) in src/voter_api/services/audit_service.py
- [x] T020 Create FastAPI app factory with lifespan handler (init async engine on startup, dispose on shutdown), register exception handlers, configure OpenAPI metadata in src/voter_api/main.py
- [x] T021 Create root API router with /api/v1 prefix, include all sub-routers, implement CORS middleware (configurable origins) and security headers middleware in src/voter_api/api/router.py and src/voter_api/api/middleware.py
- [x] T022 Implement auth API endpoints: POST /auth/login (OAuth2PasswordBearer), POST /auth/refresh, GET /auth/me, GET /users (admin), POST /users (admin), GET /health (no auth) per OpenAPI spec in src/voter_api/api/v1/auth.py
- [x] T023 Setup Alembic with async template (alembic init -t async), configure env.py with async engine, import geoalchemy2 for spatial type registration, set sqlalchemy.url from config in alembic/
- [x] T024 Create initial Alembic migration: CREATE EXTENSION IF NOT EXISTS postgis, create users table, create audit_logs table with all indexes per data-model.md in alembic/versions/
- [x] T025 Create Typer CLI root app with serve command (uvicorn runner with --reload flag) in src/voter_api/cli/app.py, implement db subcommands (upgrade, downgrade, current) calling Alembic programmatically in src/voter_api/cli/db_cmd.py
- [x] T026 Implement user management CLI commands: create user (interactive prompts for username, email, password, role), list users (table output) in src/voter_api/cli/user_cmd.py
- [x] T027 Create shared test conftest with fixtures: async engine (test DB), async session (per-test transaction rollback), httpx AsyncClient (test app), authenticated user tokens (admin, analyst, viewer), sample user factory in tests/conftest.py
- [x] T028 [P] Write unit tests for core config (env parsing, defaults, validation), security (JWT encode/decode, password hash/verify), logging setup, and auth/common schema validation in tests/unit/test_core/ and tests/unit/test_schemas/
- [x] T029 Implement data sensitivity tier classification: define SensitivityTier enum (government_sourced, system_generated), create a field-level annotation system to tag Pydantic response schema fields by tier (government-sourced: all SoS voter file fields; system-generated: validated addresses, manual geocoding coordinates, analysis results) per FR-022 in src/voter_api/core/sensitivity.py
- [x] T030 Implement field-level access control: create a response serializer that inspects the requesting user's role and excludes system_generated-tier fields for viewer-role users, integrate with FastAPI dependency injection so analyst/admin see all fields while viewers see only government-sourced fields per FR-024 in src/voter_api/core/dependencies.py
- [x] T031 [P] Implement rate limiting middleware with configurable per-endpoint limits per constitution Principle VII in src/voter_api/api/middleware.py
- [x] T031b [P] Implement background task runner abstraction: define a BackgroundTaskRunner protocol with submit_task(coroutine) → job_id, get_status(job_id) → status, and an in-process FastAPI BackgroundTasks implementation. Used by geocoding batch, analysis runs, and async exports. Enables future swap to Celery/ARQ without service layer changes in src/voter_api/core/background.py

**Checkpoint**: Foundation ready — database, auth, audit, data sensitivity tiers, rate limiting, background task runner, API framework, CLI, and test infrastructure operational. User story implementation can now begin.

---

## Phase 3: User Story 1 — Voter Data Ingestion (Priority: P1) MVP

**Goal**: Import raw voter files from the Georgia Secretary of State into the system. Parse CSV with automatic delimiter/encoding detection, validate records, upsert (insert new / update existing), soft-delete absent voters, and generate import diff reports.

**Independent Test**: Import a sample voter CSV file via API and CLI; verify records appear in the database with correct data, import job shows success/failure counts, re-import updates existing records and soft-deletes absent ones, diff report shows added/removed/updated.

### Implementation for User Story 1

- [x] T032 [P] [US1] Create Voter model with all 53 SoS columns (county, voter_registration_number, status, name fields, residence address components, mailing address, registered districts, dates, demographics), soft-delete fields (present_in_latest_import, soft_deleted_at), import tracking FKs (last_seen_in_import_id, first_seen_in_import_id), and all indexes per data-model.md in src/voter_api/models/voter.py
- [x] T033 [P] [US1] Create ImportJob model with id, file_name, file_type, status (pending/running/completed/failed), record counts (total, succeeded, failed, inserted, updated, soft_deleted), error_log (JSONB), triggered_by, timestamps, last_processed_offset (INTEGER for checkpoint/resume) per data-model.md in src/voter_api/models/import_job.py
- [x] T034 [US1] Create Alembic migration for voters table (with all B-tree indexes and composite name search index) and import_jobs table per data-model.md in alembic/versions/
- [x] T035 [P] [US1] Create voter Pydantic v2 schemas: VoterSummaryResponse, VoterDetailResponse (with nested AddressResponse, MailingAddressResponse, RegisteredDistrictsResponse including combo, land_lot, land_district), include date_of_last_contact and voter_created_date in VoterDetailResponse, full_address computed field from address components per OpenAPI spec in src/voter_api/schemas/voter.py
- [x] T036 [P] [US1] Create import Pydantic v2 schemas: ImportJobResponse, PaginatedImportJobResponse, ImportDiffResponse (with added/removed/updated voter lists) per OpenAPI spec in src/voter_api/schemas/imports.py
- [x] T037 [US1] Implement CSV parser with automatic delimiter detection (comma, pipe, tab), encoding detection (UTF-8, Latin-1), pandas chunked reading (configurable batch size), and column mapping for GA SoS 53-column format in src/voter_api/lib/importer/parser.py
- [x] T038 [US1] Implement voter record validation: required fields (county, voter_registration_number, status, last_name, first_name), format constraints (birth_year 4-digit 1900–current, dates parseable, status enum), flag address-less voters as un-geocodable, uniqueness tracking in src/voter_api/lib/importer/validator.py
- [x] T039 [US1] Implement import diff generation: compare current import against previous import to identify added, removed (soft-deleted), and updated voter records in src/voter_api/lib/importer/differ.py
- [x] T040 [US1] Define importer public API: import_voter_file(file_path, options) → ImportResult with re-exports from parser, validator, differ in src/voter_api/lib/importer/__init__.py
- [x] T041 [US1] Implement import service: create ImportJob, process file in chunks via importer library, bulk upsert voters (insert new, update existing by voter_registration_number), soft-delete absent voters (set present_in_latest_import=False, soft_deleted_at), restore reappearing voters, generate diff report, update job status/counts, with checkpoint tracking for resumability (persist last-processed batch offset in ImportJob for resume-on-failure per SC-009) in src/voter_api/services/import_service.py
- [x] T042 [US1] Implement import API endpoints: POST /imports/voters (multipart file upload, admin only), GET /imports (list jobs with file_type and status filters, paginated), GET /imports/{job_id} (job status), GET /imports/{job_id}/diff (diff report) per OpenAPI spec in src/voter_api/api/v1/imports.py
- [x] T043 [US1] Implement voter import CLI command: `import voters <file>` with progress bar (tqdm), county filter option, summary output in src/voter_api/cli/import_cmd.py
- [x] T044 [P] [US1] Write unit tests for importer library: parser (delimiter detection, encoding handling, chunked reading, column mapping, reject undetectable files), validator (required field checks, format validation, address-less voter flagging, edge cases), differ (added/removed/updated detection) in tests/unit/lib/test_importer/
- [ ] T045 [US1] Write integration tests for voter import: API endpoint (file upload, job status, diff report, resume after failure), service (upsert logic, soft-delete, re-import), CLI command in tests/integration/

**Checkpoint**: Voter data can be imported from SoS CSV files. Records are stored, validated, and tracked with import diff reports. Interrupted imports can resume from checkpoint. This is the MVP foundation.

---

## Phase 4: User Story 2 — Address Geocoding (Priority: P2)

**Goal**: Geocode voter addresses to obtain latitude/longitude coordinates via pluggable providers. Support batch geocoding with rate limiting, per-provider caching, manual coordinate entry, and primary location designation.

**Independent Test**: Import voters (US1), trigger batch geocoding, verify coordinates are stored and geographically reasonable. Test manual coordinate entry, primary designation, and cache hit behavior.

### Implementation for User Story 2

- [x] T046 [P] [US2] Create GeocodedLocation model with id, voter_id (FK), latitude, longitude, point (GEOMETRY(Point, 4326)), confidence_score, source_type, is_primary, input_address, geocoded_at, unique constraint on (voter_id, source_type), spatial GIST index per data-model.md in src/voter_api/models/geocoded_location.py
- [x] T046b [P] [US2] Create GeocodingJob model with id, provider, county, force_regeocode, status (pending/running/completed/failed), progress counts (total_records, processed, succeeded, failed, cache_hits), last_processed_voter_offset (INTEGER for checkpoint/resume), error_log (JSONB), triggered_by, timestamps per data-model.md in src/voter_api/models/geocoding_job.py
- [x] T047 [P] [US2] Create GeocoderCache model with id, provider, normalized_address, latitude, longitude, confidence_score, raw_response (JSONB), cached_at, unique constraint on (provider, normalized_address) per data-model.md in src/voter_api/models/geocoder_cache.py
- [x] T048 [US2] Create Alembic migration for geocoded_locations table (with spatial index, voter_id index, partial primary index), geocoder_cache table, and geocoding_jobs table per data-model.md in alembic/versions/
- [x] T049 [P] [US2] Create geocoding Pydantic v2 schemas: GeocodedLocationResponse, ManualGeocodingRequest (with lat/lon validation -90/90 and -180/180), GeocodingJobResponse (with progress tracking) per OpenAPI spec in src/voter_api/schemas/geocoding.py
- [x] T050 [US2] Implement address reconstruction from voter address components (street number, pre-direction, street name, type, post-direction, apt/unit, city, zip) and USPS Publication 28 normalization (directional abbreviations, street type abbreviations, uppercase, collapse whitespace), gracefully handling empty/null components without extra spaces or commas in src/voter_api/lib/geocoder/address.py
- [x] T051 [US2] Define abstract BaseGeocoder interface (ABC) with async geocode(address) → GeocodingResult, async batch_geocode(addresses) → list[GeocodingResult], provider_name property in src/voter_api/lib/geocoder/base.py
- [x] T052 [US2] Implement per-provider database caching layer: lookup by (provider, normalized_address), store new results, cache hit/miss tracking in src/voter_api/lib/geocoder/cache.py
- [x] T053 [US2] Implement US Census Bureau geocoder provider: async httpx calls to Census Geocoding API, parse response for coordinates and confidence, handle errors and timeouts in src/voter_api/lib/geocoder/census.py
- [x] T054 [US2] Define geocoder public API: geocode(address, provider), batch_geocode(addresses, provider), provider registry/factory for provider selection in src/voter_api/lib/geocoder/__init__.py
- [x] T055 [US2] Implement geocoding service: create GeocodingJob record, submit via BackgroundTaskRunner, find un-geocoded voters, reconstruct addresses, batch process with rate limiting (asyncio.Semaphore), cache lookups, store GeocodedLocations, set first result as primary, update GeocodingJob progress counts, handle manual entries, set-primary logic, queue failed geocoding attempts for automatic retry (max 3 retries, exponential backoff starting at 60s), track processing checkpoint in GeocodingJob.last_processed_voter_offset for resumability (resume from last-processed voter on failure per SC-009) in src/voter_api/services/geocoding_service.py
- [x] T056 [US2] Implement geocoding API endpoints: POST /geocoding/batch (trigger batch, admin only), GET /geocoding/status/{job_id} (progress), GET /geocoding/cache/stats (per-provider stats) per OpenAPI spec in src/voter_api/api/v1/geocoding.py
- [x] T057 [US2] Implement voter geocoded-location API endpoints: GET /voters/{id}/geocoded-locations (list all), POST /voters/{id}/geocoded-locations/manual (manual entry), PUT /voters/{id}/geocoded-locations/{loc_id}/set-primary (admin only) per OpenAPI spec in src/voter_api/api/v1/voters.py
- [x] T058 [US2] Implement geocoding CLI commands: `geocode --county --provider --force` (batch), `geocode manual <voter_id> --lat --lon` (manual entry) in src/voter_api/cli/geocode_cmd.py
- [x] T059 [P] [US2] Write unit tests for geocoder library: address normalization (component reconstruction, USPS abbreviations, edge cases with missing components — empty pre-direction, no apt/unit, partial addresses), cache (hit/miss, per-provider isolation), census provider (response parsing, error handling) in tests/unit/lib/test_geocoder/
- [ ] T060 [US2] Write integration tests for geocoding: batch API endpoint, retry behavior, manual entry, set-primary, cache stats, CLI commands in tests/integration/

**Checkpoint**: Voter addresses can be geocoded via the Census Bureau provider. Coordinates are cached per provider, failed geocoding retried automatically, manual entries supported, and one location per voter is designated primary.

---

## Phase 5: User Story 3 — District & Precinct Boundary Ingestion (Priority: P3)

**Goal**: Import geospatial boundary data (shapefiles, GeoJSON) for all 15 district/precinct types. Validate geometry, store as PostGIS MultiPolygons, and support spatial queries (point-in-polygon, list, filter).

**Independent Test**: Import a shapefile and GeoJSON boundary file, verify boundaries are stored with valid geometry. Run a point-in-polygon query with known coordinates to confirm spatial indexing works.

### Implementation for User Story 3

- [x] T061 [P] [US3] Create Boundary model with id, name, boundary_type (enum of 15 types), boundary_identifier, source (state/county), county, geometry (GEOMETRY(MultiPolygon, 4326)), effective_date, properties (JSONB), timestamps, unique constraint on (boundary_type, boundary_identifier, county), spatial GIST index per data-model.md in src/voter_api/models/boundary.py
- [x] T062 [US3] Create Alembic migration for boundaries table with spatial index, type index, county index, and composite unique index per data-model.md in alembic/versions/
- [x] T063 [P] [US3] Create boundary Pydantic v2 schemas: BoundarySummaryResponse (no geometry), BoundaryDetailResponse (with GeoJSON geometry), PaginatedBoundaryResponse per OpenAPI spec in src/voter_api/schemas/boundary.py
- [x] T064 [US3] Implement shapefile reader using GeoPandas with pyogrio engine: read .shp files, transform CRS to EPSG:4326 via .to_crs(), convert geometries to MultiPolygon, extract metadata attributes in src/voter_api/lib/boundary_loader/shapefile.py
- [x] T065 [P] [US3] Implement GeoJSON reader: parse .geojson files, validate geometry (ST_IsValid), convert to MultiPolygon if needed, extract properties in src/voter_api/lib/boundary_loader/geojson.py
- [x] T066 [US3] Define boundary_loader public API: load_boundaries(file_path, boundary_type, source, county) → list[BoundaryData] with format auto-detection (depends on T064 and T065) in src/voter_api/lib/boundary_loader/__init__.py
- [x] T067 [US3] Implement boundary service: import boundaries (validate geometry, repair with ST_MakeValid, upsert by type+identifier+county), list boundaries (paginated, filtered), get by ID (with/without geometry), find containing point (ST_Contains spatial query), detect overlapping boundaries of the same type using ST_Overlaps and flag for administrative review per spec edge case in src/voter_api/services/boundary_service.py
- [x] T068 [US3] Implement boundary API endpoints: GET /boundaries (list with type/county/source filters), GET /boundaries/{id} (detail with optional geometry), GET /boundaries/containing-point (lat/lon query with optional type filter) per OpenAPI spec in src/voter_api/api/v1/boundaries.py
- [x] T069 [US3] Add boundary import endpoint: POST /imports/boundaries (multipart file upload with boundary_type, source, county params, admin only) to src/voter_api/api/v1/imports.py
- [x] T070 [US3] Add boundary import CLI command: `import boundaries <file> --type <boundary_type> --source <state|county> --county <name>` to src/voter_api/cli/import_cmd.py
- [x] T071 [P] [US3] Write unit tests for boundary_loader library: shapefile reading (CRS transform, MultiPolygon conversion), GeoJSON reading (validation, property extraction), format detection in tests/unit/lib/test_boundary_loader/
- [ ] T072 [US3] Write integration tests for boundary: import API (shapefile + GeoJSON), list/get endpoints, point-in-polygon spatial query, overlap detection, CLI commands in tests/integration/

**Checkpoint**: District and precinct boundaries can be imported from shapefiles and GeoJSON. Spatial queries correctly identify which boundaries contain a given point. Overlapping boundaries are flagged.

---

## Phase 6: User Story 4 — Voter Registration Location Analysis (Priority: P4)

**Goal**: Run point-in-polygon analysis to determine each voter's physical district/precinct from their geocoded location. Compare against registered assignments to identify mismatches. Store results as timestamped snapshots for historical comparison.

**Independent Test**: Load known voter records with geocoded addresses and known boundary data. Run analysis and verify the system correctly identifies voters inside/outside their registered districts. Compare two runs to see changes.

### Implementation for User Story 4

- [x] T073 [P] [US4] Create AnalysisRun model with id, triggered_by, status (pending/running/completed/failed), summary counts (total_voters_analyzed, match_count, mismatch_count, unable_to_analyze_count), notes, last_processed_voter_offset (INTEGER for checkpoint/resume), timestamps per data-model.md in src/voter_api/models/analysis_run.py
- [x] T074 [P] [US4] Create AnalysisResult model with id, analysis_run_id (FK), voter_id (FK), determined_boundaries (JSONB map), registered_boundaries (JSONB map), match_status (enum), mismatch_details (JSONB array), analyzed_at, unique on (analysis_run_id, voter_id) per data-model.md in src/voter_api/models/analysis_result.py
- [x] T075 [US4] Create Alembic migration for analysis_runs and analysis_results tables with all indexes per data-model.md in alembic/versions/
- [x] T076 [P] [US4] Create analysis Pydantic v2 schemas: AnalysisRunResponse, PaginatedAnalysisRunResponse, AnalysisResultResponse (with embedded VoterSummaryResponse), PaginatedAnalysisResultResponse, AnalysisComparisonResponse per OpenAPI spec in src/voter_api/schemas/analysis.py
- [x] T077 [US4] Implement point-in-polygon spatial queries: for each voter's primary GeocodedLocation, find all containing Boundary records grouped by boundary_type using ST_Contains in src/voter_api/lib/analyzer/spatial.py
- [x] T078 [US4] Implement registered vs determined boundary comparison: extract voter's registered district values, compare against spatially-determined values per boundary type, classify mismatch (match, mismatch-district, mismatch-precinct, mismatch-both, unable-to-analyze), generate mismatch_details, handle boundary-line edge case with deterministic assignment via consistent tie-breaking rule and flag for manual review per US4 scenario 3 in src/voter_api/lib/analyzer/comparator.py
- [x] T079 [US4] Define analyzer public API: run_analysis(county, filters) → AnalysisRunResult with exports from spatial and comparator in src/voter_api/lib/analyzer/__init__.py
- [x] T080 [US4] Implement analysis service: create AnalysisRun snapshot, submit via BackgroundTaskRunner, find eligible voters (geocoded with primary location), batch spatial analysis, compare registrations, store AnalysisResults, update run summary counts, support run comparison (diff two runs), with checkpoint tracking for resumability (persist last-processed voter batch in AnalysisRun.last_processed_voter_offset for resume-on-failure per SC-009) in src/voter_api/services/analysis_service.py
- [x] T081 [US4] Implement analysis API endpoints: POST /analysis/runs (trigger, admin/analyst), GET /analysis/runs (list, admin/analyst — analysis data is system-generated per FR-022), GET /analysis/runs/{id} (detail, admin/analyst), GET /analysis/runs/{id}/results (paginated with match_status/county filters, admin/analyst), GET /analysis/compare (compare two runs, admin/analyst) per OpenAPI spec and FR-022/FR-024 in src/voter_api/api/v1/analysis.py
- [x] T082 [US4] Implement analysis CLI command: `analyze --county --notes` with progress output and summary in src/voter_api/cli/analyze_cmd.py
- [x] T083 [P] [US4] Write unit tests for analyzer library: spatial queries (mock PostGIS, test boundary matching), comparator (match/mismatch classification, boundary-line tie-breaking, un-geocoded voter exclusion, edge cases) in tests/unit/lib/test_analyzer/
- [ ] T084 [US4] Write integration tests for analysis: trigger run API, verify results, resume after failure, compare runs, filter by match_status, CLI command in tests/integration/

**Checkpoint**: Full analytical pipeline operational. Voters are spatially matched to districts/precincts, mismatches identified, boundary-line cases flagged, and results stored as historical snapshots for comparison.

---

## Phase 7: User Story 5 — Voter Search & Query (Priority: P5)

**Goal**: Enable searching voters by multiple parameters (name, address, voter ID, registration status, county, district, precinct) with partial matching, combined filters (AND logic), and paginated results.

**Independent Test**: Load voter records, perform searches by each supported parameter and combined parameters. Verify correct results with proper pagination metadata.

### Implementation for User Story 5

- [ ] T085 [US5] Implement voter service with multi-parameter search (voter_registration_number exact, first_name/last_name partial ILIKE, county, city, zipcode, status, districts, present_in_latest_import), AND logic for combined filters, configurable pagination, and eager-loaded relationships in src/voter_api/services/voter_service.py
- [ ] T086 [US5] Implement GET /voters search endpoint with all query parameters (voter_registration_number, first_name, last_name, county, residence_city, residence_zipcode, status, congressional_district, state_senate_district, state_house_district, county_precinct, present_in_latest_import, page, page_size) per OpenAPI spec in src/voter_api/api/v1/voters.py
- [ ] T087 [US5] Implement GET /voters/{voter_id} detail endpoint with full voter data including primary_geocoded_location, nested address/district objects per OpenAPI spec in src/voter_api/api/v1/voters.py
- [ ] T088 [US5] Create Alembic migration adding any additional composite search indexes on voters table for query performance optimization
- [ ] T089 [P] [US5] Write unit tests for voter_service search logic: single-param queries, combined filters, partial name matching, pagination, empty results in tests/unit/test_services/test_voter_service.py
- [ ] T090 [US5] Write integration tests for voter search API: all query parameters, combined filters, pagination, voter detail endpoint in tests/integration/test_api/test_voters.py
- [ ] T091 [US5] Write contract tests for voter endpoints validating response shapes against OpenAPI spec in tests/contract/test_openapi/test_voters.py

**Checkpoint**: Voters are fully searchable by any combination of parameters with paginated results. Individual voter details include all related data.

---

## Phase 8: User Story 6 — Bulk Data Export (Priority: P6)

**Goal**: Export voter data in CSV, JSON, and GeoJSON formats with support for filtering (county, status, district, match_status). Large exports process asynchronously with download link when complete.

**Independent Test**: Load voter records with analysis results, request exports with various filters and formats. Verify output files contain correct records in expected formats.

### Implementation for User Story 6

- [ ] T092 [P] [US6] Create ExportJob model with id, filters (JSONB), output_format (csv/json/geojson), status, record_count, file_path, file_size_bytes, triggered_by, timestamps per data-model.md in src/voter_api/models/export_job.py
- [ ] T093 [US6] Create Alembic migration for export_jobs table with status and triggered_by indexes per data-model.md in alembic/versions/
- [ ] T094 [P] [US6] Create export Pydantic v2 schemas: ExportRequest (output_format, filters with county/status/district/match_status/analysis_run_id), ExportJobResponse (with download_url), PaginatedExportJobResponse per OpenAPI spec in src/voter_api/schemas/export.py
- [ ] T095 [US6] Implement CSV export writer: configurable column selection, header row, streaming write for large datasets in src/voter_api/lib/exporter/csv_writer.py
- [ ] T096 [P] [US6] Implement JSON export writer: array of voter objects, streaming JSON array for large datasets in src/voter_api/lib/exporter/json_writer.py
- [ ] T097 [P] [US6] Implement GeoJSON export writer: FeatureCollection with Point geometries from primary geocoded location, voter properties as Feature attributes in src/voter_api/lib/exporter/geojson_writer.py
- [ ] T098 [US6] Define exporter public API: export_voters(voters_query, format, output_path) → ExportResult with format registry in src/voter_api/lib/exporter/__init__.py
- [ ] T099 [US6] Implement export service: create ExportJob, submit via BackgroundTaskRunner, apply filters (reuse voter_service query builder), select format writer, process asynchronously for large datasets (>50K records), write to EXPORT_DIR, update job with file path/size/count, ensure snapshot consistency for concurrent operations by capturing snapshot timestamp at export initiation using REPEATABLE READ isolation per spec edge case in src/voter_api/services/export_service.py
- [ ] T100 [US6] Implement export API endpoints: POST /exports (request export, admin only), GET /exports (list jobs), GET /exports/{id} (job status), GET /exports/{id}/download (stream file) per OpenAPI spec in src/voter_api/api/v1/exports.py
- [ ] T101 [US6] Implement export CLI command: `export --format <csv|json|geojson> --county --match-status --output` with progress in src/voter_api/cli/export_cmd.py
- [ ] T102 [P] [US6] Write unit tests for exporter library: CSV writer (columns, escaping), JSON writer (structure, streaming), GeoJSON writer (FeatureCollection, geometry) in tests/unit/lib/test_exporter/
- [ ] T103 [US6] Write integration tests for export: API endpoints (request, status, download), filter application, snapshot consistency, all formats, CLI command in tests/integration/

**Checkpoint**: Data can be exported in all three formats with filters. Large exports complete asynchronously with snapshot consistency and download links.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, contract validation, performance, and end-to-end verification

- [ ] T104 Write comprehensive contract tests for all API endpoint groups (auth, imports, geocoding, boundaries, analysis, exports) validating response schemas against OpenAPI spec in tests/contract/test_openapi/
- [ ] T105 [P] Add request size limits to file upload endpoints (imports/voters, imports/boundaries) in src/voter_api/api/v1/imports.py
- [ ] T106 Run full test suite, identify coverage gaps, and add targeted tests to achieve 90% threshold across all modules
- [ ] T107 [P] Validate all public API surfaces have type hints and Google-style docstrings per constitution Principle II across src/voter_api/
- [ ] T108 Run complete quickstart.md workflow end-to-end (setup, import voters, import boundaries, geocode, analyze, search, export) and verify all operations succeed
- [ ] T109 [P] Create performance test fixtures: generate synthetic voter dataset (500,000 records), boundary dataset (all 15 types, ~2,000 boundaries), and pre-geocoded locations in tests/performance/conftest.py and tests/performance/fixtures/
- [ ] T110 [P] Write performance benchmark for SC-001: import 500K voter CSV completes within 30 minutes, measure wall-clock time and memory usage in tests/performance/test_import_benchmark.py
- [ ] T111 [P] Write performance benchmark for SC-002: validate 95%+ geocoding success rate against a representative address sample using Census Bureau provider in tests/performance/test_geocoding_benchmark.py
- [ ] T112 [P] Write performance benchmark for SC-003: import boundary dataset (shapefile) and verify spatial indexing completes within 10 minutes in tests/performance/test_boundary_benchmark.py
- [ ] T113 [P] Write performance benchmark for SC-004: run location analysis for 500K geocoded voters against all loaded boundaries and verify completion within 60 minutes in tests/performance/test_analysis_benchmark.py
- [ ] T114 [P] Write performance benchmark for SC-005: execute voter search queries across all parameter combinations against 500K records and verify p95 latency under 2 seconds in tests/performance/test_search_benchmark.py
- [ ] T115 [P] Write performance benchmark for SC-006: export 500K records in each format (CSV, JSON, GeoJSON) and verify completion within 15 minutes per format in tests/performance/test_export_benchmark.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3–8)**: All depend on Foundational phase completion
  - US1 (P1) can start immediately after Foundational
  - US2 (P2) depends on US1 (needs voters to geocode)
  - US3 (P3) can start independently after Foundational (no voter dependency)
  - US4 (P4) depends on US2 (needs geocoded locations) AND US3 (needs boundaries)
  - US5 (P5) depends on US1 (needs voters to search) — can start after US1
  - US6 (P6) depends on US1 (needs voters to export) — enhanced by US4 (match_status filter)
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

```text
Foundational ─┬─► US1 (Voter Ingestion) ─┬─► US2 (Geocoding) ──┬─► US4 (Analysis)
              │                           ├─► US5 (Search)       │
              │                           └─► US6 (Export) ◄─────┘
              └─► US3 (Boundaries) ──────────────────────────────┘
```

- **US1 → US2**: Geocoding requires imported voter records with addresses
- **US2 + US3 → US4**: Analysis requires geocoded locations AND loaded boundaries
- **US1 → US5**: Search requires voter data in the database
- **US1 → US6**: Export requires voter data; enhanced by US4 for match_status filters
- **US3**: Can run in parallel with US1/US2 (independent boundary data)

### Within Each User Story

- Models before services (services depend on ORM models)
- Schemas can run in parallel with models (independent Pydantic definitions)
- Library implementations before services (services orchestrate libraries)
- Services before API endpoints (endpoints call services)
- API endpoints before CLI commands (CLI can reuse service patterns)
- Unit tests in parallel with integration tests where possible
- All code before final integration tests

### Parallel Opportunities

**Phase 1** — all [P] tasks (T003–T007) can run in parallel after T001–T002:
```
T001 → T002 → [T003, T004, T005, T006, T007] in parallel
```

**Phase 2** — multiple parallel tracks:
```
T008 → T011 → T017 → T018 → T022 (config → DB → DI → auth service → auth API)
T010 → [T013, T014] in parallel (base model → user model + audit model)
[T009, T012, T015, T016] all in parallel (logging, security, schemas)
T023 → T024 (alembic setup → first migration)
T025 → T026 (CLI app → user CLI, sequential)
T029 → T030 (sensitivity tiers → field-level access control)
[T028, T031] in parallel with other tracks (unit tests, rate limiting)
```

**Phase 3 (US1)** — model and schema pairs in parallel:
```
[T032, T033] in parallel → T034 (models → migration)
[T035, T036] in parallel (schemas — independent of models)
T037 → T038 → T039 → T040 (library sequence: parser → validator → differ → API)
T041 → T042 → T043 (service → API → CLI)
[T044] in parallel with integration (unit tests independent)
```

**Across stories** — US1 and US3 can run in parallel:
```
After Foundational: [US1 team, US3 team] in parallel
US2 starts after US1 completes
US4 starts after US2 + US3 complete
US5 can start after US1 completes (parallel with US2/US3)
```

---

## Parallel Example: User Story 1

```bash
# Launch models in parallel:
Task: "Create Voter model in src/voter_api/models/voter.py"
Task: "Create ImportJob model in src/voter_api/models/import_job.py"

# Launch schemas in parallel (independent of models):
Task: "Create voter schemas in src/voter_api/schemas/voter.py"
Task: "Create import schemas in src/voter_api/schemas/imports.py"

# After models complete, create migration:
Task: "Create Alembic migration for voters and import_jobs"

# Library tasks (sequential — each builds on previous):
Task: "Implement CSV parser in src/voter_api/lib/importer/parser.py"
Task: "Implement record validator in src/voter_api/lib/importer/validator.py"
Task: "Implement diff generator in src/voter_api/lib/importer/differ.py"

# Unit tests can run in parallel with service implementation:
Task: "Write unit tests for importer library"  # parallel
Task: "Implement import service"               # parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 — Voter Data Ingestion
4. **STOP and VALIDATE**: Import a real GA SoS voter file, verify records, test diff reports
5. Deploy/demo if ready — voters can be imported and tracked

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add **US1** (Voter Ingestion) → Test → Deploy/Demo (**MVP!**)
3. Add **US3** (Boundaries) → Test → Boundaries queryable
4. Add **US2** (Geocoding) → Test → Addresses geocoded
5. Add **US4** (Analysis) → Test → Mismatches detected (**core value delivered**)
6. Add **US5** (Search) → Test → Day-to-day querying enabled
7. Add **US6** (Export) → Test → Data interoperability
8. Polish → Contract tests, final coverage

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - **Developer A**: US1 (Voter Ingestion) → US2 (Geocoding)
   - **Developer B**: US3 (Boundaries)
   - After US1+US2+US3: **Developer A**: US4 (Analysis)
   - **Developer B**: US5 (Search) + US6 (Export)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All code must pass `ruff check .` and `ruff format --check .` before commit
- All public functions/classes must have type hints and Google-style docstrings
- The project uses Python 3.13 (per pyproject.toml) and uv for all Python operations
