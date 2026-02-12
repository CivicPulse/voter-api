# Tasks: Static Dataset Publishing

**Input**: Design documents from `/specs/002-static-dataset-publish/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi-changes.yaml

**Tests**: Included — constitution requires 90% coverage and tests for all new code.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install dependencies needed for S3/R2 integration

- [ ] T001 Add boto3 runtime dependency via `uv add boto3`
- [ ] T002 Add moto[s3] dev dependency via `uv add --dev "moto[s3]"`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create publisher library skeleton, R2 configuration, and CLI registration that ALL user stories depend on

- [ ] T003 [P] Create publisher data types (DatasetEntry, PublishResult, ManifestData dataclasses) in src/voter_api/lib/publisher/types.py per data-model.md manifest schema
- [ ] T004 [P] Add R2 configuration settings (r2_enabled, r2_account_id, r2_access_key_id, r2_secret_access_key, r2_bucket, r2_public_url, r2_prefix, r2_manifest_ttl) to src/voter_api/core/config.py using Pydantic Settings pattern
- [ ] T005 [P] Update .env.example with R2 environment variables (R2_ENABLED, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, R2_PUBLIC_URL, R2_PREFIX, R2_MANIFEST_TTL) with placeholder values and comments
- [ ] T006 [P] Create src/voter_api/lib/publisher/__init__.py with module docstring and empty __all__ list (will be populated as modules are implemented)
- [ ] T007 Register publish_app subcommand in src/voter_api/cli/app.py following existing pattern (import publish_app from publish_cmd, add_typer with name="publish")

**Checkpoint**: Foundation ready — publisher library skeleton exists, R2 config is validated, CLI group is registered

---

## Phase 3: User Story 1 — Generate and Publish Boundary Datasets (Priority: P1) MVP

**Goal**: Admin can run `voter-api publish datasets` to generate per-type and combined boundary GeoJSON files and upload them to R2 with a manifest

**Independent Test**: Run `uv run voter-api publish datasets` with a configured R2 bucket containing imported boundaries. Verify files appear in the bucket with correct GeoJSON structure matching the existing `/api/v1/boundaries/geojson` endpoint output.

### Implementation for User Story 1

- [ ] T008 [P] [US1] Implement generate_boundary_geojson(boundaries, output_path) in src/voter_api/lib/publisher/generator.py — streaming GeoJSON FeatureCollection writer using same feature structure as existing endpoint (id, geometry, properties with name/boundary_type/boundary_identifier/source/county). Handle invalid geometries by skipping with warning.
- [ ] T009 [P] [US1] Implement R2 storage operations in src/voter_api/lib/publisher/storage.py — create_r2_client() with R2-specific boto3 config (checksum workaround, endpoint URL, region="auto"), upload_file() with TransferConfig (25 MB multipart threshold), upload_manifest(), validate_config() to verify bucket access before publishing
- [ ] T010 [P] [US1] Implement build_manifest() in src/voter_api/lib/publisher/manifest.py — constructs manifest dict from list of DatasetEntry objects per data-model.md schema (version, published_at, publisher_version, datasets map)
- [ ] T011 [US1] Implement publish service in src/voter_api/services/publish_service.py — publish_datasets() orchestrates: query all boundaries from DB, group by boundary_type, call generator for each type + combined all-boundaries file, upload files in order (per-type first, combined second, manifest last), return PublishResult. Include boundary_to_feature_dict() to convert Boundary ORM to feature dict matching existing endpoint structure.
- [ ] T012 [US1] Implement CLI `publish datasets` command in src/voter_api/cli/publish_cmd.py — create publish_app Typer, add `datasets` command that initializes DB engine, creates R2 client, validates config, calls publish_datasets service, displays progress (record counts, file sizes, upload status via typer.echo). Follow async pattern from existing CLI commands (asyncio.run wrapper).
- [ ] T013 [US1] Update public API exports in src/voter_api/lib/publisher/__init__.py — export generate_boundary_geojson, create_r2_client, upload_file, upload_manifest, validate_config, build_manifest, DatasetEntry, PublishResult, ManifestData in __all__

### Tests for User Story 1

- [ ] T014 [P] [US1] Unit tests for generator in tests/unit/lib/test_publisher/test_generator.py — test valid boundary dicts produce correct GeoJSON FeatureCollection, test streaming write produces valid JSON, test invalid geometries are skipped with warning, test empty input produces no file, test feature structure matches existing endpoint format
- [ ] T015 [P] [US1] Unit tests for storage in tests/unit/lib/test_publisher/test_storage.py — use moto mock S3: test create_r2_client returns configured client, test upload_file uploads with correct content-type and key, test upload_manifest uploads valid JSON, test validate_config succeeds for valid bucket and raises for invalid, test multipart threshold is respected for large files
- [ ] T016 [P] [US1] Unit tests for manifest builder in tests/unit/lib/test_publisher/test_manifest.py — test build_manifest produces correct schema with version/published_at/datasets, test dataset entries are correctly serialized, test empty dataset list

**Checkpoint**: `voter-api publish datasets` generates and uploads all boundary GeoJSON files + manifest to R2. Publishable as a standalone CLI tool.

---

## Phase 4: User Story 4 — API Redirects to Static Files (Priority: P1)

**Goal**: The existing `/api/v1/boundaries/geojson` endpoint returns HTTP 302 redirects to published static files on R2 when available, falling back to database when not

**Independent Test**: Publish datasets, then `curl -v http://localhost:8000/api/v1/boundaries/geojson` and verify HTTP 302 with Location header pointing to R2 public URL. Verify `?boundary_type=congressional` redirects to the type-specific file. Verify fallback to 200 when R2 is not configured.

### Implementation for User Story 4

- [ ] T017 [P] [US4] Implement ManifestCache class in src/voter_api/lib/publisher/manifest.py — TTL-based in-memory cache (get/set/invalidate/is_stale), thread-safe, configurable TTL from settings
- [ ] T018 [P] [US4] Implement get_redirect_url(manifest, boundary_type, county, source) in src/voter_api/lib/publisher/manifest.py — returns public_url from manifest if exact match exists (no filters → all-boundaries, boundary_type filter → type-specific file), returns None for county/source filters or missing datasets
- [ ] T019 [US4] Add fetch_manifest(client, bucket, key) to src/voter_api/lib/publisher/storage.py — downloads and parses manifest.json from R2, returns ManifestData or None if not found
- [ ] T020 [US4] Modify get_boundaries_geojson() in src/voter_api/api/v1/boundaries.py — check r2_enabled setting, if enabled: refresh manifest cache if stale (via asyncio.to_thread wrapping fetch_manifest), call get_redirect_url, if URL found return RedirectResponse(url, status_code=302), otherwise fall through to existing database logic unchanged
- [ ] T021 [US4] Update public API exports in src/voter_api/lib/publisher/__init__.py — add ManifestCache, get_redirect_url, fetch_manifest to __all__

### Tests for User Story 4

- [ ] T022 [P] [US4] Unit tests for ManifestCache and redirect URL logic in tests/unit/lib/test_publisher/test_manifest.py — test cache returns None when empty, test cache returns data within TTL, test cache reports stale after TTL expires, test invalidate clears cache, test get_redirect_url returns all-boundaries URL for no filters, test returns type-specific URL for boundary_type filter, test returns None for county/source filters, test returns None when manifest is empty
- [ ] T023 [P] [US4] Integration tests for API redirect in tests/integration/test_publish_redirect.py — test endpoint returns 302 with correct Location when manifest cached, test endpoint returns 200 from database when R2 not configured, test endpoint returns 200 fallback when no matching static file for county filter, test endpoint returns 302 for boundary_type filter matching published dataset

**Checkpoint**: GeoJSON endpoint transparently redirects to R2 for matching requests. Existing behavior fully preserved when R2 is not configured.

---

## Phase 5: User Story 2 — Filter Published Datasets (Priority: P2)

**Goal**: Admin can selectively publish by boundary type, county, or source to update only changed datasets

**Independent Test**: Run `uv run voter-api publish datasets --boundary-type congressional` and verify only congressional.geojson is uploaded/updated. Run with `--source state` and verify only state-sourced boundaries are included.

### Implementation for User Story 2

- [ ] T024 [US2] Add filter options (--boundary-type, --county, --source) to the `datasets` command in src/voter_api/cli/publish_cmd.py — pass filters through to publish_datasets service call
- [ ] T025 [US2] Extend publish_datasets() in src/voter_api/services/publish_service.py — apply boundary_type/county/source filters to DB query, when filters active: skip combined all-boundaries file, fetch existing manifest from R2 via fetch_manifest, merge new dataset entries into existing manifest (preserving entries for types not being republished), upload merged manifest
- [ ] T026 [US2] Integration tests for filtered publishing in tests/integration/test_publish_cli.py — test boundary_type filter publishes only matching type file, test county filter restricts boundaries within types, test source filter restricts by source, test filtered publish merges into existing manifest without removing other entries, test no-boundaries-match scenario reports no datasets

**Checkpoint**: Selective publishing works. Admin can incrementally update individual boundary type datasets.

---

## Phase 6: User Story 3 — Track Published Dataset Metadata (Priority: P3)

**Goal**: Admin can check what datasets are published, when, and their sizes via CLI and API

**Independent Test**: Run `uv run voter-api publish status` after publishing datasets and verify output shows dataset names, record counts, file sizes, and timestamps.

### Implementation for User Story 3

- [ ] T027 [P] [US3] Create publish response schemas (PublishStatusResponse, PublishedDatasetInfo) in src/voter_api/schemas/publish.py per contracts/openapi-changes.yaml — configured/manifest_loaded/manifest_published_at/manifest_cached_at fields plus datasets list
- [ ] T028 [US3] Implement CLI `publish status` command in src/voter_api/cli/publish_cmd.py — fetches manifest from R2 via storage.fetch_manifest, displays formatted table (dataset name, record count, file size, published_at) using typer.echo, handles not-configured and no-datasets-published cases
- [ ] T029 [US3] Implement GET /boundaries/publish/status API endpoint in src/voter_api/api/v1/boundaries.py — requires admin auth, returns PublishStatusResponse from cached manifest data (configured flag, manifest metadata, dataset list)
- [ ] T030 [US3] Contract tests for publish status endpoint in tests/contract/test_publish_contract.py — validate response matches PublishStatusResponse schema, test configured=false when R2 disabled, test datasets list matches manifest entries

**Checkpoint**: Full observability into published datasets via both CLI and API.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates and final validation

- [ ] T031 Run `uv run ruff check .` and `uv run ruff format .` on all new and modified files
- [ ] T032 Verify test coverage meets 90% threshold via `uv run pytest --cov=voter_api --cov-report=term-missing`
- [ ] T033 Validate quickstart.md scenarios by reviewing CLI command help output and error messages

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (dependencies installed)
- **US1 (Phase 3)**: Depends on Phase 2 (types, config, CLI registration)
- **US4 (Phase 4)**: Depends on Phase 3 (manifest schema, storage operations)
- **US2 (Phase 5)**: Depends on Phase 3 (publish command to extend) and Phase 4 (fetch_manifest for merging)
- **US3 (Phase 6)**: Depends on Phase 3 (manifest exists to report on) and Phase 4 (fetch_manifest)
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
Phase 5: US2 (Filters)    Phase 6: US3 (Status)  ← can run in parallel
    ↓ ↙
Phase 7: Polish
```

### Within Each User Story

- Library modules (generator, storage, manifest) before service layer
- Service layer before CLI/API integration
- Implementation before tests (tests validate implementation)
- All [P] tasks within a phase can run in parallel

### Parallel Opportunities

**Phase 2** — T003, T004, T005, T006 are all different files, run in parallel
**Phase 3** — T008, T009, T010 are independent library modules, run in parallel; T014, T015, T016 are independent test files, run in parallel
**Phase 4** — T017, T018 are independent additions; T022, T023 are independent test files
**Phase 5 & 6** — US2 and US3 can run in parallel after US4 completes

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
3. Complete Phase 6: US3 — Status Tracking (4 tasks)
4. Complete Phase 7: Polish (3 tasks)
5. Full-featured static dataset publishing with filters, status, and redirect

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in the same phase
- [Story] label maps task to specific user story for traceability
- US1 and US4 are both P1 priority but US4 depends on US1 (needs publish before redirect)
- US2 and US3 can run in parallel after US4 since they share no dependencies
- Commit after each completed phase per constitution commit cadence rule
- All new code requires type hints, Google-style docstrings, and ruff compliance
