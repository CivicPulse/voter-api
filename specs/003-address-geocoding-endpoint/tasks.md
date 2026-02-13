# Tasks: Single-Address Geocoding Endpoint

**Input**: Design documents from `/specs/003-address-geocoding-endpoint/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/openapi.yaml, quickstart.md

**Tests**: Included. Testing is NON-NEGOTIABLE per project constitution (90% coverage threshold). Plan.md specifies unit, integration, and contract test files.

**Organization**: Tasks grouped by user story. Five user stories across three priority tiers:
- **P1**: US1 (Geocode), US5 (Point Lookup) — MVP
- **P2**: US2 (Caching), US4 (Verify/Autocomplete)
- **P3**: US3 (Error Handling)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No new project initialization needed — this feature extends the existing voter-api project. All dependencies (FastAPI, SQLAlchemy, GeoAlchemy2, httpx, Alembic) are already installed.

*(No tasks — proceed to Phase 2)*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that ALL user stories depend on — the canonical Address model, database migration, shared library functions, and Pydantic response schemas. The `addresses` table is the key architectural addition (see data-model.md).

**CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Create Address ORM model with parsed component columns (`street_number`, `pre_direction`, `street_name`, `street_type`, `post_direction`, `apt_unit`, `city`, `state`, `zipcode`), `normalized_address` TEXT NOT NULL with UNIQUE constraint, `created_at`/`updated_at` timestamps, prefix-search index (`text_pattern_ops`), zipcode index, and `(city, state)` composite index; register in `src/voter_api/models/__init__.py` — file: `src/voter_api/models/address.py`
- [X] T002 [P] Add Pydantic v2 request/response schemas for all three endpoints matching `contracts/openapi.yaml`: `AddressGeocodeResponse` (formatted_address, latitude, longitude, confidence, metadata), `AddressVerifyResponse` (input_address, normalized_address, is_well_formed, validation, suggestions), `PointLookupResponse` (latitude, longitude, accuracy, districts), `ValidationDetail`, `AddressSuggestion`, `DistrictInfo` — file: `src/voter_api/schemas/geocoding.py`
- [X] T003 [P] Add `normalize_freeform_address(address: str) -> str` function — uppercase, trim, collapse whitespace, apply USPS Pub 28 abbreviations using existing `STREET_TYPE_MAP` and `DIRECTIONAL_MAP` with word-boundary matching to avoid false positives — file: `src/voter_api/lib/geocoder/address.py`
- [X] T004 [P] Add `AddressComponents` dataclass (street_number, pre_direction, street_name, street_type, post_direction, apt_unit, city, state, zipcode) with a `to_dict() -> dict` method (keys matching Address model columns), and `parse_address_components(address: str) -> AddressComponents` function — split on commas to separate street line/city/state+zip, extract ZIP (5-digit or ZIP+4), state abbreviation, street number (leading digits), street type (known USPS abbreviations), remaining tokens as street name. This is the **single** freeform address parser used by both the geocode service (T012 via `.to_dict()`) and the verify endpoint (T027 for validation). — file: `src/voter_api/lib/geocoder/address.py`
- [X] T005 [P] Create point_lookup module with Georgia bounding box constants (`GA_MIN_LAT=30.355`, `GA_MAX_LAT=35.001`, `GA_MIN_LNG=-85.606`, `GA_MAX_LNG=-80.840`), `validate_georgia_coordinates(lat, lng)` that raises `ValueError` for out-of-area coordinates, and `meters_to_degrees(meters, latitude) -> float` using latitude-dependent approximation per research.md Section 6 — file: `src/voter_api/lib/geocoder/point_lookup.py`
- [X] T006 [P] Add `address_id` UUID FK column (nullable, references `addresses.id`) and SQLAlchemy relationship to GeocoderCache model (depends on T001) — file: `src/voter_api/models/geocoder_cache.py`
- [X] T007 [P] Add `residence_address_id` UUID FK column (nullable, references `addresses.id`) and SQLAlchemy relationship to Voter model; inline residence address fields permanently retained (depends on T001) — file: `src/voter_api/models/voter.py`
- [X] T008 Create Alembic migration revision: CREATE TABLE `addresses` with all columns, UNIQUE constraint on `normalized_address`, prefix-search index (`text_pattern_ops`), zipcode index, `(city, state)` index; ALTER TABLE `geocoder_cache` ADD COLUMN `address_id` UUID FK + index; ALTER TABLE `voters` ADD COLUMN `residence_address_id` UUID FK + index (depends on T001, T006, T007)
- [X] T009 Export `normalize_freeform_address`, `parse_address_components`, `AddressComponents`, `validate_georgia_coordinates`, `meters_to_degrees` from `src/voter_api/lib/geocoder/__init__.py` (depends on T003, T004, T005)

**Checkpoint**: Foundation ready — `addresses` table migrated, GeocoderCache and Voter FKs in place, shared schemas and library functions available. User story implementation can now begin.

---

## Phase 3: User Story 1 — Geocode a Single Address (Priority: P1) MVP

**Goal**: Expose `GET /api/v1/geocoding/geocode` that accepts a freeform address string and returns geographic coordinates with confidence score. Cache-first strategy with canonical address upsert on successful geocode (FR-006).

**Independent Test**: Send `GET /api/v1/geocoding/geocode?address=100+Peachtree+St+NW,+Atlanta,+GA+30303` with valid JWT and verify response contains `formatted_address`, `latitude`, `longitude`, `confidence`, and `metadata`.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T010 [P] [US1] Add unit tests for `normalize_freeform_address()` (various casings, extra whitespace, USPS abbreviations, empty string, whitespace-only, 500-char boundary) and `parse_address_components()` (full Georgia address, partial address, address with unit/apt, edge cases) — file: `tests/unit/lib/test_geocoder/test_address.py`
- [X] T011 [P] [US1] Create integration test stubs for `GET /geocoding/geocode` endpoint: authenticated valid address returns 200 with required fields, unauthenticated returns 401, geocoded result outside Georgia returns 422 (FR-023) — file: `tests/integration/test_api/test_geocode_endpoint.py`

### Implementation for User Story 1

- [X] T012 [US1] Create AddressService with `upsert_from_geocode(normalized_address, components, session) -> Address` (ON CONFLICT DO UPDATE SET updated_at=now(), RETURNING id) and `get_by_normalized(normalized_address, session) -> Address | None` — file: `src/voter_api/services/address_service.py`
- [X] T013 [US1] Add `geocode_single_address(session, address_string) -> AddressGeocodeResponse` to GeocodingService — normalize input via `normalize_freeform_address()`, check geocoder cache, on miss call provider, on success parse components + upsert Address row via AddressService + store cache entry with `address_id` FK, validate result coordinates against Georgia bbox (FR-023), set `metadata.cached` flag, return `AddressGeocodeResponse` — file: `src/voter_api/services/geocoding_service.py`
- [X] T014 [US1] Add `GET /geocoding/geocode` endpoint with `Depends(get_current_user)` JWT auth, `address` query parameter (`Query`, `min_length=1`, `max_length=500`, strip whitespace), reject empty/whitespace-only with 422 (FR-007), call `geocode_single_address()`, return `AddressGeocodeResponse` (200) — file: `src/voter_api/api/v1/geocoding.py`
- [X] T015 [US1] Complete integration tests for geocode endpoint: valid address (200), empty address (422), whitespace-only (422), address > 500 chars (422), out-of-Georgia result (422); include a timing assertion that uncached geocode responses complete within 5 seconds (SC-001, using a mocked provider with realistic latency) — file: `tests/integration/test_api/test_geocode_endpoint.py`
- [X] T016 [P] [US1] Create contract tests validating geocode 200 response against `AddressGeocodeResponse` schema from `contracts/openapi.yaml` — file: `tests/contract/test_geocoding_contract.py`

**Checkpoint**: Geocode endpoint fully functional — uncached addresses geocoded via Census provider, results cached with Address row upsert. Test with Swagger UI or curl per quickstart.md.

---

## Phase 4: User Story 5 — Point Lookup for Boundary Districts (Priority: P1)

**Goal**: Expose `GET /api/v1/geocoding/point-lookup` that accepts lat/lng coordinates (optional GPS accuracy radius) and returns all boundary districts containing that point via PostGIS spatial query.

**Independent Test**: Send `GET /api/v1/geocoding/point-lookup?lat=33.749&lng=-84.388` with valid JWT and verify response contains `districts[]` with boundary_type, name, boundary_identifier, boundary_id, and metadata for matching boundaries.

### Tests for User Story 5

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T017 [P] [US5] Create unit tests for `validate_georgia_coordinates()` (inside GA, outside GA, boundary edges) and `meters_to_degrees()` (various latitudes, zero meters, 100m max, accuracy at Georgia latitude range) — file: `tests/unit/lib/test_geocoder/test_point_lookup.py`
- [ ] T018 [P] [US5] Create integration test stubs for `GET /geocoding/point-lookup`: valid GA coords with loaded boundaries returns districts (200), out-of-GA coords returns 422, accuracy > 100m returns 422, coords with no matching boundaries returns empty list (200), missing params returns 422, unauthenticated returns 401 — file: `tests/integration/test_api/test_point_lookup_endpoint.py`

### Implementation for User Story 5

- [ ] T019 [US5] Add `find_boundaries_at_point(session, lat, lng, accuracy_meters=None) -> list[Boundary]` to BoundaryService — use `ST_Contains(geometry, ST_SetSRID(ST_MakePoint(lng, lat), 4326))` for exact point; when `accuracy_meters` provided, use `ST_DWithin(geometry, point, meters_to_degrees(accuracy_meters, lat))` for expanded search — file: `src/voter_api/services/boundary_service.py`
- [ ] T020 [US5] Add `GET /geocoding/point-lookup` endpoint with `Depends(get_current_user)` JWT auth, `lat`/`lng` required float query params, optional `accuracy` float query param (`le=100`, reject > 100 with 422 per FR-020), call `validate_georgia_coordinates()` (422 if outside per FR-021), call `find_boundaries_at_point()`, map results to `DistrictInfo` list, return `PointLookupResponse` — file: `src/voter_api/api/v1/geocoding.py`
- [ ] T021 [US5] Complete integration tests for point-lookup endpoint with all scenarios; include a timing assertion that point-lookup responses complete within 1 second (SC-007) — file: `tests/integration/test_api/test_point_lookup_endpoint.py`
- [ ] T022 [P] [US5] Add contract tests for point-lookup endpoint validating 200 response against `PointLookupResponse` schema — file: `tests/contract/test_geocoding_contract.py`

**Checkpoint**: Both P1 stories complete — MVP delivered. Geocode + point-lookup form the end-to-end "address lookup" flow for the frontend.

---

## Phase 5: User Story 2 — Cached Results Returned Instantly (Priority: P2)

**Goal**: Repeat geocoding requests return cached results instantly with `metadata.cached: true`, without calling the external provider.

**Independent Test**: Geocode an address, then submit the same address again. Verify second response has `metadata.cached: true` and no provider call is made.

**Note**: Caching behavior is inherent in `geocode_single_address()` (Phase 3). This phase validates and verifies that behavior explicitly.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T023 [P] [US2] Add cache-behavior integration tests: geocode address then submit same address, verify `metadata.cached=true` on second response, verify no second provider call (mock provider), verify cached response time < 500ms (SC-002), verify new results stored in cache — file: `tests/integration/test_api/test_geocode_endpoint.py`

### Implementation for User Story 2

- [ ] T024 [US2] Verify and ensure `geocode_single_address()` correctly sets `metadata.cached=true` on cache hit (skips provider call) and `metadata.cached=false` on cache miss (calls provider, stores result); fix if not already correct — file: `src/voter_api/services/geocoding_service.py`

**Checkpoint**: Cache behavior validated — repeat lookups skip external provider, metadata accurately reflects source.

---

## Phase 6: User Story 4 — Verify and Autocomplete an Address (Priority: P2)

**Goal**: Expose `GET /api/v1/geocoding/verify` that accepts a partial/malformed address and returns USPS-normalized form, component validation feedback (present/missing/malformed), and up to 10 ranked autocomplete suggestions from the canonical address store.

**Independent Test**: Send `GET /api/v1/geocoding/verify?address=100+Peachtree` with valid JWT and verify response contains `normalized_address`, `is_well_formed: false`, `validation` with missing components (city, state, zip), and `suggestions[]`.

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T025 [P] [US4] Create unit tests for `validate_address_components()`: well-formed address reports all present, partial address reports missing components, malformed ZIP detected, USPS abbreviation normalization applied. NOTE: `parse_address_components()` tests are in T010 (test_address.py), not here — file: `tests/unit/lib/test_geocoder/test_verify.py`
- [ ] T026 [P] [US4] Create integration test stubs for `GET /geocoding/verify`: partial address returns suggestions (200), malformed address returns normalized form + validation (200), input < 5 chars returns empty suggestions (200, FR-017), well-formed address confirms completeness (200), empty address (422), unauthenticated (401), empty cache returns empty suggestions (200) — file: `tests/integration/test_api/test_verify_endpoint.py`

### Implementation for User Story 4

- [ ] T027 [P] [US4] Create verify.py library module with: `ValidationFeedback` dataclass (present_components, missing_components, malformed_components, is_well_formed), `validate_address_components(components: AddressComponents) -> ValidationFeedback` — checks required fields (street_number, street_name, city, state, zip), validates ZIP format (5-digit or ZIP+4), and `BaseSuggestionSource` ABC with `async search(query, limit) -> list` for pluggable providers (FR-015). NOTE: `AddressComponents` dataclass and `parse_address_components()` are defined in address.py (T004) — import from there, do NOT duplicate. — file: `src/voter_api/lib/geocoder/verify.py`
- [ ] T028 [US4] Add `prefix_search(session, normalized_prefix, limit=10) -> list[AddressSuggestion]` to AddressService — query `addresses` table with `normalized_address LIKE :prefix || '%'` using `text_pattern_ops` index, JOIN `geocoder_cache` for coordinates and confidence_score, use DISTINCT ON to pick the highest-confidence provider result per address, ORDER BY `normalized_address`, LIMIT 10, return list of AddressSuggestion per data-model.md query pattern — file: `src/voter_api/services/address_service.py`
- [ ] T029 [US4] Create `CacheSuggestionSource(BaseSuggestionSource)` in the **service layer** that wraps `AddressService.prefix_search()` to provide suggestions from the canonical address store. Must NOT live in `lib/` — library modules must remain independently importable without service-layer dependencies (Constitution Principle I) (depends on T027, T028) — file: `src/voter_api/services/address_service.py`
- [ ] T030 [US4] Add `verify_address(session, address_string) -> AddressVerifyResponse` to GeocodingService — normalize via `normalize_freeform_address()`, parse via `parse_address_components()` (from address.py), validate via `validate_address_components()`, if input >= 5 chars run `prefix_search()` else return empty suggestions list (FR-017), assemble and return `AddressVerifyResponse` — file: `src/voter_api/services/geocoding_service.py`
- [ ] T031 [US4] Add `GET /geocoding/verify` endpoint with `Depends(get_current_user)` JWT auth, `address` query param (`Query`, `min_length=1`, `max_length=500`), call `verify_address()`, return `AddressVerifyResponse` (200), return 422 on empty/too-long validation error — file: `src/voter_api/api/v1/geocoding.py`
- [ ] T032 [US4] Complete integration tests for verify endpoint with all scenarios; include a timing assertion that verify responses complete within 500ms (SC-005) — file: `tests/integration/test_api/test_verify_endpoint.py`
- [ ] T033 [P] [US4] Add contract tests for verify endpoint validating 200 response against `AddressVerifyResponse` schema — file: `tests/contract/test_geocoding_contract.py`
- [ ] T034 [US4] Export `parse_freeform_address`, `validate_address_components`, `BaseSuggestionSource` from `src/voter_api/lib/geocoder/__init__.py` (note: `CacheSuggestionSource` is in `services/address_service.py`, not exported from lib)

**Checkpoint**: Verify endpoint fully functional — addresses normalized with USPS abbreviations, components validated, autocomplete suggestions returned from canonical address store.

---

## Phase 7: User Story 3 — Graceful Geocoding Failure Handling (Priority: P3)

**Goal**: Clear, actionable HTTP error responses distinguishing validation failures (422), no-match (404), and provider outages (502) with single retry and ~4s total provider timeout budget (FR-009).

**Independent Test**: Submit empty address (expect 422), unmatchable address (expect 404), simulate provider timeout (expect 502). Verify each returns correct HTTP status and descriptive error message.

**Note**: Basic validation (422) is handled in Phase 3. This phase adds provider error differentiation: `GeocodingProviderError` exception class, census.py modification, retry logic, and HTTP 502 response.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T035 [P] [US3] Add unit tests for CensusGeocoder error differentiation: `httpx.TimeoutException` raises `GeocodingProviderError`, `httpx.HTTPStatusError` raises `GeocodingProviderError`, successful response with empty `addressMatches` returns `None`, successful response with matches returns `GeocodingResult` — file: `tests/unit/lib/test_geocoder/test_census.py`
- [ ] T036 [P] [US3] Add integration tests for geocode endpoint error paths: empty address returns 422, whitespace-only returns 422, address > 500 chars returns 422, unmatchable address returns 404 with descriptive message, provider timeout returns 502 with retry suggestion — file: `tests/integration/test_api/test_geocode_endpoint.py`

### Implementation for User Story 3

- [ ] T037 [P] [US3] Create `GeocodingProviderError` exception class with `provider_name`, `message`, and optional `status_code` attributes — file: `src/voter_api/lib/geocoder/base.py`
- [ ] T038 [US3] Modify `CensusGeocoder.geocode()` to raise `GeocodingProviderError` on `httpx.TimeoutException`, `httpx.HTTPStatusError`, and connection errors instead of returning `None`; continue returning `None` only when provider responds successfully but `addressMatches` is empty (depends on T037) — file: `src/voter_api/lib/geocoder/census.py`
- [ ] T039 [US3] Add retry logic to `geocode_single_address()` — instantiate geocoder with **2s timeout** (override the 30s default via `CensusGeocoder(timeout=2.0)` or equivalent), wrap provider call in single retry (2 attempts max, 4s total budget per FR-009), catch `GeocodingProviderError` on both failures, return appropriate error for API layer. NOTE: batch geocoding retains the existing 30s default — the 2s timeout applies only to the single-address endpoint path (depends on T038) — file: `src/voter_api/services/geocoding_service.py`
- [ ] T040 [US3] Update `GET /geocoding/geocode` endpoint error handling — map `None` return to `HTTPException(404, "Address could not be geocoded")`, catch `GeocodingProviderError` and return `HTTPException(502, "Geocoding provider is temporarily unavailable. Please retry later.")` per FR-009 — file: `src/voter_api/api/v1/geocoding.py`
- [ ] T041 [US3] Update batch geocoding `_geocode_with_retry()` to catch `GeocodingProviderError` — maintain existing retry/skip behavior, log error per voter to avoid breaking batch pipeline (depends on T038) — file: `src/voter_api/services/geocoding_service.py`

**Checkpoint**: All geocode error paths return correct HTTP status codes with descriptive messages. Provider transport failures get one retry before 502. Unmatchable addresses return 404. Batch pipeline unaffected.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Data backfill, final validation, and code quality checks.

- [ ] T042 [P] Create Alembic data migration to backfill existing `geocoder_cache` rows with `address_id` (parse components from `normalized_address`, upsert into `addresses` table, set FK) — idempotent, safe to re-run per data-model.md Migration 2. NOTE: Does NOT backfill voters — voter `residence_address_id` is set by the post-import processing pipeline (T046), not by a one-time migration, because raw voter addresses require validation and geocoding before linking to the canonical address store.
- [ ] T043 [P] Run `uv run ruff check .` and `uv run ruff format --check .` on all modified and new files — fix any violations
- [ ] T044 Run full test suite with coverage: `uv run pytest --cov=voter_api --cov-report=term-missing` — verify 90% threshold met
- [ ] T045 Run quickstart.md validation — verify all curl examples from `specs/003-address-geocoding-endpoint/quickstart.md` work correctly against running dev server
- [ ] T046 Define post-import address processing pipeline — create a service method (or CLI command) that picks up voters with `residence_address_id IS NULL`, normalizes their inline address components via `reconstruct_address()`, attempts geocoding via the existing provider infrastructure, and on success upserts into the `addresses` table and sets the voter FK. Failed/un-geocodable addresses leave the FK as NULL for manual review. Should build on existing batch geocoding patterns. Idempotent and safe to re-run. Include unit/integration tests. — files: `src/voter_api/services/address_service.py`, `tests/unit/test_services/test_address_service.py`, `tests/integration/test_api/test_address_backfill.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 2)**: No dependencies — can start immediately
- **US1 Geocode (Phase 3)**: Depends on Phase 2 (needs Address model, `normalize_freeform_address`, schemas, migration)
- **US5 Point Lookup (Phase 4)**: Depends on Phase 2 (needs `validate_georgia_coordinates`, `meters_to_degrees`, schemas) — can run in PARALLEL with Phase 3
- **US2 Cache (Phase 5)**: Depends on Phase 3 (validates geocode endpoint caching behavior)
- **US4 Verify (Phase 6)**: Depends on Phase 2 + Phase 3 (needs Address model, `normalize_freeform_address`, AddressService from US1)
- **US3 Error Handling (Phase 7)**: Depends on Phase 3 (modifies geocode endpoint error path)
- **Polish (Phase 8)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependency on other stories
- **US5 (P1)**: Can start after Foundational — PARALLEL with US1 (independent files)
- **US2 (P2)**: Depends on US1 (validates its caching behavior)
- **US4 (P2)**: Depends on US1 (uses AddressService created in US1 for prefix search)
- **US3 (P3)**: Depends on US1 (modifies its error handling path)

### Within Each User Story

1. Tests written first (ensure they FAIL)
2. Library modules before services
3. Services before endpoints
4. Integration tests completed after endpoint implementation
5. Contract tests can run in parallel with integration tests
6. Commit after each task or logical group

### Parallel Opportunities

- **Phase 2**: T001–T005 all parallel (different files, no shared dependencies)
- **Phase 3**: T010 ∥ T011 (test files); T016 ∥ T015 (contract vs integration tests)
- **Phase 4**: T017 ∥ T018 (test files); T022 ∥ T021 (contract vs integration tests)
- **Phase 6**: T025 ∥ T026 ∥ T027 (test_verify.py ∥ verify.py ∥ address_service.py)
- **Phase 7**: T035 ∥ T036 ∥ T037 (tests and base.py — different files)
- **Cross-story**: US1 (Phase 3) ∥ US5 (Phase 4) — both P1, independent after Phase 2
- **Phase 8**: T042 ∥ T043 (data migration ∥ lint — different concerns)

---

## Parallel Example: US1 + US5 (MVP)

```text
# After Phase 2 completes, launch both P1 stories in parallel:

Stream A — US1 (Geocode):
  T010, T011 (tests, parallel)
  → T012 (AddressService)
  → T013 (geocode_single_address)
  → T014 (GET /geocoding/geocode)
  → T015 (complete integration tests)
  → T016 (contract tests, parallel with T015)

Stream B — US5 (Point Lookup):
  T017, T018 (tests, parallel)
  → T019 (find_boundaries_at_point)
  → T020 (GET /geocoding/point-lookup)
  → T021 (complete integration tests)
  → T022 (contract tests, parallel with T021)

# After US1 completes, US2/US3/US4 can start:

Stream C (US2): T023 → T024
Stream D (US4): T025, T026 (parallel) → T027, T028 → T029 → T030 → T031 → T032, T033, T034
Stream E (US3): T035, T036, T037 (parallel) → T038 → T039 → T040 → T041
```

---

## Implementation Strategy

### MVP First (P1 Stories Only)

1. Complete Phase 2: Foundational (Address model, migration, shared libs)
2. Complete Phase 3: US1 — Geocode endpoint
3. Complete Phase 4: US5 — Point-lookup endpoint
4. **STOP and VALIDATE**: Both P1 stories independently testable
5. Deploy/demo — core "address lookup" feature operational for frontend

### Incremental Delivery

1. Phase 2 → Foundation ready
2. US1 (Phase 3) → Geocode endpoint live → **MVP!**
3. US5 (Phase 4) → Point lookup live → Full P1 delivered (frontend unblocked)
4. US2 (Phase 5) → Cache behavior validated → Performance confirmed
5. US4 (Phase 6) → Verify/autocomplete live → Form-fill UX enabled
6. US3 (Phase 7) → Error handling hardened → Production-ready error responses
7. Phase 8 → Backfill complete, full test suite at 90%+ coverage, all validation green

### Parallel Team Strategy

With multiple developers after Phase 2:

- **Developer A**: US1 (Geocode) → US2 (Cache) → US3 (Errors) → Polish
- **Developer B**: US5 (Point Lookup) → US4 (Verify) → Polish

### File Touch Summary

| File | Phases | Action |
|------|--------|--------|
| `src/voter_api/models/address.py` | 2 | NEW |
| `src/voter_api/models/__init__.py` | 2 | MODIFY |
| `src/voter_api/models/geocoder_cache.py` | 2 | MODIFY |
| `src/voter_api/models/voter.py` | 2 | MODIFY |
| `src/voter_api/schemas/geocoding.py` | 2 | MODIFY |
| `src/voter_api/lib/geocoder/address.py` | 2 | MODIFY |
| `src/voter_api/lib/geocoder/point_lookup.py` | 2, 4 | NEW |
| `src/voter_api/lib/geocoder/verify.py` | 6 | NEW |
| `src/voter_api/lib/geocoder/base.py` | 7 | MODIFY |
| `src/voter_api/lib/geocoder/census.py` | 7 | MODIFY |
| `src/voter_api/lib/geocoder/__init__.py` | 2, 6 | MODIFY |
| `src/voter_api/services/address_service.py` | 3, 6, 8 | NEW |
| `src/voter_api/services/geocoding_service.py` | 3, 5, 6, 7, 8 | MODIFY |
| `src/voter_api/services/boundary_service.py` | 4 | MODIFY |
| `src/voter_api/api/v1/geocoding.py` | 3, 4, 6, 7 | MODIFY |
| `tests/unit/lib/test_geocoder/test_address.py` | 3 | MODIFY |
| `tests/unit/lib/test_geocoder/test_point_lookup.py` | 4 | NEW |
| `tests/unit/lib/test_geocoder/test_verify.py` | 6 | NEW |
| `tests/unit/lib/test_geocoder/test_census.py` | 7 | MODIFY |
| `tests/integration/test_api/test_geocode_endpoint.py` | 3, 5, 7 | NEW |
| `tests/integration/test_api/test_point_lookup_endpoint.py` | 4 | NEW |
| `tests/integration/test_api/test_verify_endpoint.py` | 6 | NEW |
| `tests/contract/test_geocoding_contract.py` | 3, 4, 6 | NEW |

---

## Notes

- [P] tasks = different files, no dependencies — safe for parallel execution
- [Story] label maps each task to its user story for traceability
- Each user story is independently completable and testable
- Write tests first and verify they FAIL before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate the story independently
- The `addresses` table is the key architectural addition — canonical address store referenced by geocoder_cache (FK) and voters (FK)
- Voter `residence_address_id` is set via post-import processing (T046), NOT during CSV import — the addresses table is a validated store; raw voter data must be normalized and geocoded before linking
- Prefix search for autocomplete queries the `addresses` table (not `geocoder_cache`) per data-model.md
