# Tasks: Static Dataset Publishing

**Input**: Design documents from `/specs/002-static-dataset-publish/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi-changes.yaml

**Tests**: Included — constitution requires 90% coverage and tests for all new code.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install dependencies needed for S3/R2 integration

- [x] T001 Add boto3 runtime dependency via `uv add boto3`
- [x] T002 Add moto[s3] dev dependency via `uv add --dev "moto[s3]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create publisher library skeleton, R2 configuration, and CLI registration that ALL user stories depend on

- [x] T003 [P] Create publisher data types (DatasetEntry, PublishResult, ManifestData dataclasses) in src/voter_api/lib/publisher/types.py per data-model.md manifest schema. DatasetEntry fields: name, key, public_url, content_type, record_count, file_size_bytes, boundary_type (str | None), filters (dict[str, str]), published_at (datetime). PublishResult fields: datasets (list[DatasetEntry]), manifest_key, total_records, total_size_bytes, duration_seconds. ManifestData fields: version, published_at, publisher_version, datasets (dict[str, DatasetEntry]).
- [x] T004 [P] Add R2 configuration settings to src/voter_api/core/config.py using existing Pydantic Settings pattern — add r2_enabled (bool, default False), r2_account_id (str | None), r2_access_key_id (str | None), r2_secret_access_key (str | None), r2_bucket (str | None), r2_public_url (str | None), r2_prefix (str, default ""), r2_manifest_ttl (int, default 300) fields to the Settings class with Field() descriptors
- [x] T005 [P] Update .env.example with R2 environment variables (R2_ENABLED, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_URL, R2_PREFIX, R2_MANIFEST_TTL) with placeholder values and descriptive comments
- [x] T006 [P] Create src/voter_api/lib/publisher/__init__.py with module docstring and empty __all__ list (will be populated as modules are implemented)
- [x] T007 [P] Create stub src/voter_api/cli/publish_cmd.py with publish_app = typer.Typer(name="publish", help="Publish static datasets to object storage.") and register it in src/voter_api/cli/app.py following existing _register_subcommands() pattern (import publish_app from publish_cmd, app.add_typer(publish_app))

**Checkpoint**: Foundation ready — publisher library skeleton exists, R2 config is validated, CLI group is registered

---

## Phase 3: User Story 1 — Generate and Publish Boundary Datasets (Priority: P1) MVP

**Goal**: Admin can run `voter-api publish datasets` to generate per-type and combined boundary GeoJSON files and upload them to R2 with a manifest

**Independent Test**: Run `uv run voter-api publish datasets` with a configured R2 bucket containing imported boundaries. Verify files appear in the bucket with correct GeoJSON structure matching the existing `/api/v1/boundaries/geojson` endpoint output.

### Implementation for User Story 1

- [x] T008 [P] [US1] Implement generate_boundary_geojson(boundaries, output_path) in src/voter_api/lib/publisher/generator.py — streaming GeoJSON FeatureCollection writer using same feature structure as existing endpoint (id, geometry, properties with name/boundary_type/boundary_identifier/source/county). Handle invalid geometries by skipping with warning via loguru. Return record count. Write to Path output_path as valid JSON.
- [x] T009 [P] [US1] Implement R2 storage operations in src/voter_api/lib/publisher/storage.py — create_r2_client(account_id, access_key_id, secret_access_key) with R2-specific boto3 config (checksum workaround per research.md Decision 2, endpoint URL https://{account_id}.r2.cloudflarestorage.com, region="auto"), upload_file(client, bucket, key, file_path, content_type) with TransferConfig (25 MB multipart threshold per research.md Decision 4, content_type="application/geo+json"), upload_manifest(client, bucket, key, manifest_data) as JSON, validate_config(client, bucket) to verify bucket access before publishing
- [x] T010 [P] [US1] Implement build_manifest(datasets, publisher_version) in src/voter_api/lib/publisher/manifest.py — constructs manifest dict from list of DatasetEntry objects per data-model.md schema (version "1", published_at ISO 8601, publisher_version string, datasets map keyed by dataset name)
- [x] T011 [US1] Implement publish service in src/voter_api/services/publish_service.py — publish_datasets(session, client, bucket, public_url, prefix, boundary_type=None, county=None, source=None) orchestrates: query all boundaries from DB using existing list_boundaries service, group by boundary_type, call generator for each type + combined all-boundaries file, upload files in order (per-type first, combined second, manifest last per research.md Decision 3), return PublishResult. Include boundary_to_feature_dict(boundary) to convert Boundary ORM to feature dict matching existing endpoint structure (id, geometry via to_shape/mapping, properties dict).
- [x] T012 [US1] Add `datasets` command to existing publish_app in src/voter_api/cli/publish_cmd.py — add datasets() function that initializes DB engine via get_async_session pattern, creates R2 client from settings, validates config, calls publish_datasets service, displays progress (record counts, file sizes, upload status via typer.echo). Handle no-boundaries case (report and exit). Handle storage errors with clear messages. Follow async pattern from existing CLI commands (asyncio.run wrapper).
- [x] T013 [US1] Update public API exports in src/voter_api/lib/publisher/__init__.py — export generate_boundary_geojson, create_r2_client, upload_file, upload_manifest, validate_config, build_manifest, DatasetEntry, PublishResult, ManifestData in __all__

### Tests for User Story 1

- [x] T016b [US1] Integration tests for core publish CLI in tests/integration/test_publish_cli.py — test full `publish datasets` command with moto-mocked S3 bucket and test DB with imported boundaries: verify all per-type GeoJSON files + combined all-boundaries.geojson + manifest.json are uploaded to bucket, verify uploaded GeoJSON contains valid FeatureCollection with correct feature structure matching existing endpoint (properties: name, boundary_type, boundary_identifier, source, county), verify manifest.json contains entries for all uploaded datasets with correct record counts and file sizes, test no-boundaries-in-DB case reports "no datasets available" and uploads nothing, test storage-unreachable case (invalid credentials) reports clear error before generating files (FR-011)

### Tests for User Story 1

- [x] T014 [P] [US1] Unit tests for generator in tests/unit/lib/test_publisher/test_generator.py — test valid boundary dicts produce correct GeoJSON FeatureCollection with type/id/geometry/properties, test streaming write produces valid JSON, test invalid geometries are skipped with warning, test empty input produces no file or empty collection, test feature structure matches existing endpoint format (properties: name, boundary_type, boundary_identifier, source, county)
- [x] T015 [P] [US1] Unit tests for storage in tests/unit/lib/test_publisher/test_storage.py — use moto mock S3: test create_r2_client returns configured client, test upload_file uploads with correct content-type (application/geo+json) and key, test upload_manifest uploads valid JSON, test validate_config succeeds for valid bucket and raises for invalid/missing bucket, test TransferConfig multipart threshold is set to 25 MB
- [x] T016 [P] [US1] Unit tests for manifest builder in tests/unit/lib/test_publisher/test_manifest.py — test build_manifest produces correct schema with version/published_at/publisher_version/datasets map, test dataset entries are correctly serialized with all fields (name, key, public_url, content_type, record_count, file_size_bytes, boundary_type, filters, published_at), test empty dataset list produces valid manifest with empty datasets map

**Checkpoint**: `voter-api publish datasets` generates and uploads all boundary GeoJSON files + manifest to R2. Publishable as a standalone CLI tool.

---

## Phase 4: User Story 4 — API Redirects to Static Files (Priority: P1)

**Goal**: The existing `/api/v1/boundaries/geojson` endpoint returns HTTP 302 redirects to published static files on R2 when available, falling back to database when not

**Independent Test**: Publish datasets, then `curl -v http://localhost:8000/api/v1/boundaries/geojson` and verify HTTP 302 with Location header pointing to R2 public URL. Verify `?boundary_type=congressional` redirects to the type-specific file. Verify fallback to 200 when R2 is not configured.

### Implementation for User Story 4

- [ ] T017 [P] [US4] Implement ManifestCache class in src/voter_api/lib/publisher/manifest.py — TTL-based in-memory cache with __init__(ttl_seconds: int), get() -> ManifestData | None (returns cached if within TTL), set(data: ManifestData), invalidate(), is_stale() -> bool. Thread-safe using threading.Lock. Configurable TTL from r2_manifest_ttl setting.
- [ ] T018 [US4] Implement get_redirect_url(manifest, boundary_type, county, source) in src/voter_api/lib/publisher/manifest.py — returns public_url from manifest per data-model.md redirect lookup rules: no filters → datasets["all-boundaries"].public_url, boundary_type filter → datasets[boundary_type].public_url if key exists, county/source filters → None (always fallback to DB), manifest empty/None → None
- [ ] T019 [US4] Add fetch_manifest(client, bucket, key) to src/voter_api/lib/publisher/storage.py — downloads manifest.json from R2 via client.get_object(), parses JSON, constructs ManifestData with DatasetEntry objects for each dataset in the map, returns ManifestData or None if key not found (NoSuchKey exception)
- [ ] T020 [US4] Modify get_boundaries_geojson() in src/voter_api/api/v1/boundaries.py — at the start of the function: check settings.r2_enabled, if enabled: get or refresh manifest cache (use asyncio.to_thread wrapping fetch_manifest if cache is_stale), call get_redirect_url(manifest, boundary_type, county, source), if URL found return RedirectResponse(url, status_code=302), otherwise fall through to existing database logic unchanged. Import RedirectResponse from fastapi.responses. Note: if a file is deleted from R2 but the manifest still references it, consumers will receive a 404 from R2. The fix is to republish (`voter-api publish datasets`). This is acceptable per spec ("last-write-wins") and the status command (T029) shows manifest timestamps to help admins detect staleness.
- [ ] T021 [US4] Update public API exports in src/voter_api/lib/publisher/__init__.py — add ManifestCache, get_redirect_url, fetch_manifest to __all__

### Tests for User Story 4

- [ ] T022 [P] [US4] Unit tests for ManifestCache and redirect URL logic in tests/unit/lib/test_publisher/test_manifest.py — test cache get() returns None when empty, test cache get() returns data within TTL, test cache is_stale() returns True after TTL expires, test invalidate() clears cache, test get_redirect_url returns all-boundaries URL for no filters, test returns type-specific URL for boundary_type filter, test returns None for county filter, test returns None for source filter, test returns None when manifest has no matching dataset, test returns None when manifest is None
- [ ] T023 [P] [US4] Integration tests for API redirect in tests/integration/test_publish_redirect.py — test endpoint returns 302 with correct Location header when manifest is cached with matching dataset, test endpoint returns 200 GeoJSON from database when R2 not configured (r2_enabled=False), test endpoint returns 200 fallback when no matching static file for county filter, test endpoint returns 302 for boundary_type filter matching published dataset, test endpoint returns 200 when manifest is empty

**Checkpoint**: GeoJSON endpoint transparently redirects to R2 for matching requests. Existing behavior fully preserved when R2 is not configured.

---

## Phase 5: User Story 2 — Filter Published Datasets (Priority: P2)

**Goal**: Admin can selectively publish by boundary type, county, or source to update only changed datasets

**Independent Test**: Run `uv run voter-api publish datasets --boundary-type congressional` and verify only congressional.geojson is uploaded/updated. Run with `--county Fulton` and verify only boundary types containing Fulton county boundaries are regenerated.

### Implementation for User Story 2

- [ ] T024 [US2] Add filter options (--boundary-type, --county, --source) to the `datasets` command in src/voter_api/cli/publish_cmd.py — add typer.Option parameters for boundary_type (str | None), county (str | None), source (str | None), pass filters through to publish_datasets service call
- [ ] T025 [US2] Extend publish_datasets() in src/voter_api/services/publish_service.py — when boundary_type is set: regenerate only that type's file. When county or source is set: query DB to identify which boundary types contain matching boundaries (SELECT DISTINCT boundary_type WHERE county/source matches), then regenerate only those types' files. Each regenerated file always contains ALL boundaries of its type (county/source scopes which types to republish, not what data goes in them). When filters are active: skip combined all-boundaries file, fetch existing manifest from R2 via fetch_manifest, merge new dataset entries into existing manifest (preserving entries for types not being republished), upload merged manifest.

### Tests for User Story 2

- [ ] T026 [US2] Integration tests for filtered publishing in tests/integration/test_publish_cli.py — test boundary_type filter regenerates only matching type file, test county scope regenerates only types containing that county's boundaries (each file has full type data), test source scope regenerates only types containing that source's boundaries (each file has full type data), test filtered publish merges into existing manifest without removing other entries, test no-boundaries-match scenario reports no datasets to publish

**Checkpoint**: Selective publishing works. Admin can incrementally update individual boundary type datasets.

---

## Phase 6: User Story 3 — Track Published Dataset Metadata (Priority: P3)

**Goal**: Admin can check what datasets are published, when, and their sizes via CLI and API. Consumers can discover published datasets via public endpoint.

**Independent Test**: Run `uv run voter-api publish status` after publishing datasets and verify output shows dataset names, record counts, file sizes, and timestamps. Request `GET /api/v1/datasets` and verify base_url and dataset list.

### Implementation for User Story 3

- [ ] T027 [P] [US3] Create PublishStatusResponse and PublishedDatasetInfo Pydantic schemas in src/voter_api/schemas/publish.py per contracts/openapi-changes.yaml — PublishStatusResponse with configured (bool), manifest_loaded (bool), manifest_published_at (datetime | None), manifest_cached_at (datetime | None), datasets (list[PublishedDatasetInfo]). PublishedDatasetInfo with name, key, public_url, content_type (default "application/geo+json"), record_count, file_size_bytes, boundary_type (str | None), published_at.
- [ ] T028 [P] [US3] Create DatasetDiscoveryResponse and DiscoveredDataset Pydantic schemas in src/voter_api/schemas/publish.py per contracts/openapi-changes.yaml — DatasetDiscoveryResponse with base_url (HttpUrl), datasets (list[DiscoveredDataset]). DiscoveredDataset with name (str), url (HttpUrl), boundary_type (str | None), record_count (int).
- [ ] T029 [US3] Implement CLI `publish status` command in src/voter_api/cli/publish_cmd.py — fetches manifest from R2 via storage.fetch_manifest using R2 client from settings, displays formatted table (dataset name, record count, file size, published_at) using typer.echo, handles not-configured case (R2_ENABLED=false → "R2 publishing is not configured") and no-datasets-published case (no manifest found → "No datasets have been published yet")
- [ ] T030 [US3] Implement GET /boundaries/publish/status API endpoint in src/voter_api/api/v1/boundaries.py — requires admin auth (Depends on existing auth dependency), returns PublishStatusResponse from cached manifest data: configured = settings.r2_enabled, manifest_loaded from cache state, manifest metadata and dataset list from cached ManifestData
- [ ] T031 [US3] Implement GET /api/v1/datasets discovery endpoint in src/voter_api/api/v1/datasets.py (new file) — no auth required (security: []), create datasets_router APIRouter, reads r2_public_url from settings as base_url, reads cached manifest for dataset list (maps DatasetEntry to DiscoveredDataset with name/url/boundary_type/record_count), returns DatasetDiscoveryResponse. When R2 is configured but no manifest loaded: returns base_url from settings with empty datasets list. When R2 is not configured (r2_enabled=false): returns base_url as null with empty datasets list (HTTP 200, not 503). Register router in main app.
- [ ] T032 [US3] Update public API exports in src/voter_api/lib/publisher/__init__.py if needed for any new symbols added during this phase

### Tests for User Story 3

- [ ] T033 [P] [US3] Contract tests for publish status endpoint in tests/contract/test_publish_contract.py — validate response matches PublishStatusResponse schema, test configured=false when R2 disabled, test datasets list matches manifest entries when configured
- [ ] T034 [P] [US3] Contract tests for discovery endpoint in tests/contract/test_publish_contract.py — validate response matches DatasetDiscoveryResponse schema, test base_url matches R2_PUBLIC_URL setting, test datasets list reflects manifest entries, test empty datasets list when no manifest loaded, test endpoint requires no authentication
- [ ] T034b [US3] Integration tests for publish status CLI in tests/integration/test_publish_cli.py — test `publish status` command with moto-mocked S3: verify output displays dataset name, record count, file size, and published_at for each manifest entry, test R2-not-configured case displays "R2 publishing is not configured", test no-manifest-found case displays "No datasets have been published yet"
- [ ] T034c [US3] Integration tests for discovery endpoint in tests/integration/test_publish_redirect.py — test GET /api/v1/datasets returns 200 with base_url and datasets list from cached manifest, test returns base_url=null and empty datasets when R2 not configured, test returns base_url with empty datasets when R2 configured but no manifest loaded, test endpoint requires no authentication (no Authorization header needed)

**Checkpoint**: Full observability into published datasets via CLI, admin API, and public discovery endpoint.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates and final validation

- [ ] T035 Run `uv run ruff check .` and `uv run ruff format .` on all new and modified files
- [ ] T036 Verify test coverage meets 90% threshold via `uv run pytest --cov=voter_api --cov-report=term-missing`
- [ ] T037 Validate quickstart.md scenarios by reviewing CLI command help output and error messages

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (dependencies installed)
- **US1 (Phase 3)**: Depends on Phase 2 (types, config, CLI registration)
- **US4 (Phase 4)**: Depends on Phase 3 (manifest schema, storage operations)
- **US2 (Phase 5)**: Depends on Phase 3 (publish command to extend) and Phase 4 (fetch_manifest for merging)
- **US3 (Phase 6)**: Depends on Phase 3 (manifest exists to report on) and Phase 4 (fetch_manifest, ManifestCache)
- **Polish (Phase 7)**: Depends on all previous phases

### User Story Dependencies

```
Phase 1: Setup
    ↓
Phase 2: Foundational
    ↓
Phase 3: US1 (Core Publish) ← MVP
    ↓
Phase 4: US4 (API Redirect) ← completes P1
    ↓ ↘
Phase 5: US2 (Filters)    Phase 6: US3 (Status + Discovery)  ← can run in parallel
    ↓ ↙
Phase 7: Polish
```

### Within Each User Story

- Library modules (generator, storage, manifest) before service layer
- Service layer before CLI/API integration
- Implementation before tests (tests validate implementation)
- All [P] tasks within a phase can run in parallel

### Parallel Opportunities

**Phase 2** — T003, T004, T005, T006, T007 are all different files, run in parallel
**Phase 3** — T008, T009, T010 are independent library modules, run in parallel; T014, T015, T016 are independent test files, run in parallel
**Phase 4** — T017 then T018 sequentially (both modify manifest.py); T022, T023 are independent test files
**Phase 5 & 6** — US2 and US3 can run in parallel after US4 completes
**Phase 6** — T027, T028 are schema additions in same file but independent; T033, T034 are independent test blocks

---

## Parallel Example: User Story 1

```bash
# Launch all library modules in parallel (different files, no dependencies):
Task: "T008 [P] [US1] Implement generator in src/voter_api/lib/publisher/generator.py"
Task: "T009 [P] [US1] Implement storage in src/voter_api/lib/publisher/storage.py"
Task: "T010 [P] [US1] Implement manifest builder in src/voter_api/lib/publisher/manifest.py"

# Then sequentially:
Task: "T011 [US1] Implement publish service (depends on T008, T009, T010)"
Task: "T012 [US1] Implement CLI command (depends on T011)"
Task: "T013 [US1] Update __init__.py exports"

# Launch all tests in parallel:
Task: "T014 [P] [US1] Unit tests for generator"
Task: "T015 [P] [US1] Unit tests for storage"
Task: "T016 [P] [US1] Unit tests for manifest"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (2 tasks)
2. Complete Phase 2: Foundational (5 tasks)
3. Complete Phase 3: User Story 1 (9 tasks)
4. **STOP and VALIDATE**: Run `uv run voter-api publish datasets` against a test R2 bucket
5. Publishable CLI tool that generates and uploads boundary GeoJSON to R2

### Core Value (User Stories 1 + 4)

1. Complete MVP above
2. Complete Phase 4: User Story 4 (7 tasks)
3. **STOP and VALIDATE**: Verify GeoJSON endpoint redirects to R2
4. End-to-end value: publish once, redirect forever

### Full Feature (All Stories)

1. Complete Core Value above
2. Complete Phase 5: US2 — Filtered Publishing (3 tasks)
3. Complete Phase 6: US3 — Status + Discovery (8 tasks)
4. Complete Phase 7: Polish (3 tasks)
5. Full-featured static dataset publishing with filters, status, discovery, and redirect

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase
- [Story] label maps task to specific user story for traceability
- US1 and US4 are both P1 priority but US4 depends on US1 (needs publish before redirect)
- US2 and US3 can run in parallel after US4 since they share no dependencies
- Commit after each completed phase per constitution commit cadence rule
- All new code requires type hints, Google-style docstrings, and ruff compliance
