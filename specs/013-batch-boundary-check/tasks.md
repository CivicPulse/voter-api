# Tasks: Batch Boundary Check

**Input**: Design documents from `/specs/013-batch-boundary-check/`
**Branch**: `013-batch-boundary-check`
**Spec**: `specs/013-batch-boundary-check/spec.md`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire up the new files before any implementation begins.

- [x] T001 Verify `lib/analyzer/__init__.py` exports and note what `check_batch_boundaries` export will need to be added (read-only investigation step before T009)
- [x] T002 [P] Create empty stub `src/voter_api/lib/analyzer/batch_check.py` with module docstring and placeholder `check_batch_boundaries` function signature
- [x] T003 [P] Create empty test file `tests/unit/lib/test_analyzer/test_batch_check.py` with module docstring (ensure `__init__.py` exists in that test dir if needed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic response schemas must exist before library, service, and route code can reference them.

**⚠️ CRITICAL**: No user story implementation can begin until the schemas are defined.

- [x] T004 Add `ProviderResult` Pydantic model to `src/voter_api/schemas/voter.py` with fields: `source_type: str`, `is_contained: bool`
- [x] T005 Add `DistrictBoundaryResult` Pydantic model to `src/voter_api/schemas/voter.py` with fields: `boundary_id: UUID | None`, `boundary_type: str`, `boundary_identifier: str`, `has_geometry: bool`, `providers: list[ProviderResult]`
- [x] T006 Add `ProviderSummary` Pydantic model to `src/voter_api/schemas/voter.py` with fields: `source_type: str`, `latitude: float`, `longitude: float`, `confidence_score: float | None`, `districts_matched: int`, `districts_checked: int`
- [x] T007 Add `BatchBoundaryCheckResponse` Pydantic model to `src/voter_api/schemas/voter.py` with fields: `voter_id: UUID`, `districts: list[DistrictBoundaryResult]`, `provider_summary: list[ProviderSummary]`, `total_locations: int`, `total_districts: int`, `checked_at: datetime`
- [x] T008 Run `uv run ruff check . && uv run ruff format .` and confirm zero violations before continuing

**Checkpoint**: Schemas defined — all downstream code can now import and reference them.

---

## Phase 3: User Story 1 — Compare All Provider Locations (Priority: P1) 🎯 MVP

**Goal**: Admin requests the batch boundary check for a voter with multiple geocoded locations and multiple district assignments. Receives a single response with per-provider inside/outside results for every district, plus a per-provider summary.

**Independent Test**: `POST /api/v1/voters/{voter_id}/geocode/check-boundaries` with a voter that has ≥2 geocoded locations and ≥2 district assignments returns HTTP 200 with `districts` list (each entry has `providers` list) and `provider_summary` list showing matched/total counts.

### Implementation for User Story 1

- [x] T009 [US1] Implement `check_batch_boundaries()` in `src/voter_api/lib/analyzer/batch_check.py` — core happy path:
  - Load voter by `voter_id`; raise `VoterNotFoundError` if missing
  - Call `extract_registered_boundaries(voter)` from `lib/analyzer/comparator.py` to get registered district dict
  - Query `boundaries` table WHERE `(boundary_type, boundary_identifier)` IN registered pairs — collect boundary rows and IDs
  - Query `geocoded_locations` for most-recent successful location per provider: `SELECT DISTINCT ON (source_type) * FROM geocoded_locations WHERE voter_id = :voter_id AND status = 'success' ORDER BY source_type, geocoded_at DESC` — verify the exact column name for the geometry/point field and the status enum value against the `GeocodedLocation` model before writing this query (FR-003)
  - Execute CROSS JOIN query using only the deduplicated per-provider rows: `SELECT gl.source_type, gl.latitude, gl.longitude, b.id, b.boundary_type, b.boundary_identifier, ST_Contains(b.geometry, <geometry_col>) as is_contained FROM <deduplicated_locations> gl, boundaries b WHERE b.id IN (:ids) ORDER BY gl.source_type, b.boundary_type` — the `IN (:boundary_ids)` clause ensures the GiST index on `boundaries.geometry` is used (satisfies FR-011; no full-table scan)
  - Aggregate rows into `list[DistrictBoundaryResult]` (grouped by boundary_id/type/identifier)
  - Compute `list[ProviderSummary]` (for each unique source_type: count rows where is_contained=True vs total)
  - Perform post-query reconciliation: any registered district not in DB results gets a `DistrictBoundaryResult(has_geometry=False, providers=[])` appended
  - Return `BatchBoundaryCheckResult` dataclass (internal) with all fields; include `checked_at=datetime.now(UTC)`
  - Add `VoterNotFoundError` exception class in the same module

- [x] T010 [US1] Export `check_batch_boundaries` and `VoterNotFoundError` from `src/voter_api/lib/analyzer/__init__.py`

- [x] T011 [US1] Add `check_batch_boundaries_for_voter()` service function to `src/voter_api/services/voter_service.py`:
  - Calls `check_batch_boundaries(session, voter_id)` from the library
  - Maps `VoterNotFoundError` → returns `None` (API layer will raise 404)
  - Returns `BatchBoundaryCheckResponse` Pydantic model constructed from the library result

- [x] T012 [US1] Add `POST /{voter_id}/geocode/check-boundaries` route to `src/voter_api/api/v1/voters.py`:
  - Decorator: `@voters_router.post("/{voter_id}/geocode/check-boundaries", response_model=BatchBoundaryCheckResponse, dependencies=[Depends(require_role("admin"))])`
  - Call `check_batch_boundaries_for_voter(session, voter_id)`
  - If `None`: raise `HTTPException(status_code=404, detail=VOTER_NOT_FOUND)`
  - Import and re-export: add `BatchBoundaryCheckResponse` to the schema import block in `voters.py`
  - Import `check_batch_boundaries_for_voter` from `voter_service`

- [x] T013 [US1] Write unit tests for the happy path in `tests/unit/lib/test_analyzer/test_batch_check.py`:
  - Test: voter with 2 providers × 3 district boundaries → 6 ST_Contains results correctly aggregated into 3 `DistrictBoundaryResult` entries each with 2 provider results
  - Test: `provider_summary` correctly counts `districts_matched` (only True rows) vs `districts_checked`
  - Test: registered district with no matching boundary row appears in result with `has_geometry=False` and empty `providers`
  - Test: `VoterNotFoundError` raised when voter does not exist
  - Mock the DB session and spatial query result rows

- [x] T014 [US1] Run `uv run pytest tests/unit/lib/test_analyzer/test_batch_check.py -v` and confirm all US1 tests pass

**Checkpoint**: Core functionality working — happy path fully testable with unit tests.

---

## Phase 4: User Story 2 — No Geocoded Locations Edge Case (Priority: P2)

**Goal**: Admin requests batch boundary check for a voter with no geocoded locations. System returns HTTP 200 with `total_locations=0` and empty `provider_summary`, not an error.

**Independent Test**: `POST .../geocode/check-boundaries` for a voter with zero geocoded locations returns HTTP 200 with `total_locations: 0`, `provider_summary: []`, and `districts` populated with `has_geometry` status but empty `providers` lists.

### Implementation for User Story 2

- [x] T015 [US2] Add early-return branch in `check_batch_boundaries()` in `src/voter_api/lib/analyzer/batch_check.py`:
  - After querying geocoded_locations: if the result is empty, skip the CROSS JOIN entirely
  - Still perform post-query reconciliation for registered districts (so `districts` list is populated with `has_geometry` status)
  - Return result with `total_locations=0`, `provider_summary=[]`, and `districts` showing each registered district with `has_geometry` flag

- [x] T016 [US2] Add unit test to `tests/unit/lib/test_analyzer/test_batch_check.py`:
  - Test: voter with no geocoded locations returns `total_locations=0`, `provider_summary=[]`, and `districts` list with correct `has_geometry` status (no error raised)

- [x] T017 [US2] Run `uv run pytest tests/unit/lib/test_analyzer/test_batch_check.py -v` and confirm US2 test passes

**Checkpoint**: No-locations edge case handled — US2 independently verifiable.

---

## Phase 5: User Story 3 — No District Assignments Edge Case (Priority: P3)

**Goal**: Admin requests batch boundary check for a voter with geocoded locations but no district assignments. System returns HTTP 200 with `total_districts=0` and empty `districts` list, not an error.

**Independent Test**: `POST .../geocode/check-boundaries` for a voter with geocoded locations but no registered district assignments returns HTTP 200 with `total_districts: 0`, `districts: []`, and `provider_summary` still populated with location coordinates (but `districts_matched=0, districts_checked=0`).

### Implementation for User Story 3

- [x] T018 [US3] Add early-return branch in `check_batch_boundaries()` in `src/voter_api/lib/analyzer/batch_check.py`:
  - After `extract_registered_boundaries(voter)`: if the dict is empty, skip boundary query and CROSS JOIN
  - Return result with `total_districts=0`, `districts=[]`, `provider_summary` still listing each geocoded location (with lat/lng/confidence) but `districts_matched=0, districts_checked=0`

- [x] T019 [US3] Add unit test to `tests/unit/lib/test_analyzer/test_batch_check.py`:
  - Test: voter with geocoded locations but no registered districts returns `total_districts=0`, `districts=[]`, and `provider_summary` lists all providers (with `districts_matched=0, districts_checked=0`)

- [x] T020 [US3] Run `uv run pytest tests/unit/lib/test_analyzer/test_batch_check.py -v` and confirm all unit tests pass (US1 + US2 + US3)

**Checkpoint**: All three user stories are independently tested via unit tests.

---

## Phase 6: Security Fix + Integration & E2E Tests

**Purpose**: Add Georgia bounds validation to `set_official_location_override()` (in-scope security improvement from plan.md), then write integration and E2E tests covering all user stories end-to-end.

- [x] T021 [P] Add `validate_georgia_coordinates(latitude, longitude)` call to `set_official_location_override()` in `src/voter_api/services/geocoding_service.py`:
  - Import `validate_georgia_coordinates` from `voter_api.lib.geocoder.point_lookup`
  - Call it at the start of the function, before the DB write (after the voter-not-found check)
  - The existing API route already maps `ValueError` → HTTP 422 — no route changes needed
  - Add a comment noting this guards against worldwide coordinates being stored as official location

- [x] T022 [P] Add integration tests for the new endpoint in `tests/integration/api/test_voters.py`:
  - Test: admin user gets 200 with correctly structured response (mock DB + spatial query)
  - Test: non-admin (analyst / viewer) gets 403
  - Test: unauthenticated request gets 401
  - Test: voter not found gets 404
  - Test: voter with no geocoded locations gets 200 with `total_locations=0`
  - Test: voter with no districts gets 200 with `total_districts=0`

- [x] T023 [P] Add a unit test for the Georgia validation security fix in the existing geocoding service test file (find via `tests/unit/` or `tests/integration/`):
  - Test: `set_official_location_override()` raises `ValueError` when coordinates are outside Georgia bounds
  - Test: `set_official_location_override()` proceeds normally for valid Georgia coordinates

- [x] T024 Add E2E smoke test to `tests/e2e/test_smoke.py` in the appropriate test class (add to `TestGeocoding` or add a new method to an existing voter test class):
  - Smoke test: `POST /api/v1/voters/{seeded_voter_id}/geocode/check-boundaries` with admin client → HTTP 200 with expected response structure
  - Smoke test: same endpoint with viewer client → HTTP 403

- [x] T025 Run full test suite: `uv run pytest tests/unit/ tests/integration/ -v` and confirm all tests pass

**Checkpoint**: Full test coverage for new endpoint + security fix.

---

## Phase 7: Polish & Final Validation

- [x] T026 Run `uv run ruff check . && uv run ruff format --check .` — fix any remaining violations
- [x] T027 Run `uv run pytest --cov=voter_api --cov-report=term-missing` and confirm coverage is ≥ 90%
- [x] T028 Run E2E tests locally if PostGIS is available: `DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api JWT_SECRET_KEY=test-secret-key-minimum-32-characters ELECTION_REFRESH_ENABLED=false uv run pytest tests/e2e/ -v -k "batch_boundary or check_boundaries"`
- [ ] T029 Verify the OpenAPI docs render correctly by starting the server (`uv run voter-api serve`) and checking `/docs` for the new endpoint schema; also manually time a request for a voter with ≥2 geocoded locations and ≥2 district assignments and confirm response returns in under 2 seconds (SC-002)
- [x] T030 Confirm the CROSS JOIN query uses the GiST index: run `EXPLAIN ANALYZE` via the PostgreSQL MCP on the CROSS JOIN query with a real voter and confirm `Index Scan` or `Bitmap Index Scan` on `boundaries_geometry_idx` (FR-011)
- [x] T031 Commit all changes with a conventional commit message: `feat(voters): add batch boundary check endpoint and Georgia bounds validation`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately; T002 and T003 can run in parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user story implementation (T009–T012 import these schemas)
- **Phase 3 (US1)**: Depends on Phase 2; T009 (library) blocks T010 (export) blocks T011 (service) blocks T012 (route); T013–T014 (tests) depend on T009
- **Phase 4 (US2)**: Depends on T009 being complete (modifies the same library function)
- **Phase 5 (US3)**: Depends on T015 being complete (modifies the same library function); can run after Phase 4
- **Phase 6**: T021, T022, T023 can run in parallel (different files); T024 depends on T012 (route must exist); T025 depends on T021–T024
- **Phase 7**: Depends on Phase 6 completion

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 (schemas) — foundational implementation
- **US2 (P2)**: Depends on T009 (US1 library function must exist to add branch to it)
- **US3 (P3)**: Depends on T009 and T015 (builds on same library function)

### Critical Path

T001 → T004-T007 → T009 → T010 → T011 → T012 → T013 → T015 → T018 → T022 → T025 → T026 → T029 → T030 → T031

### Parallel Opportunities

```
# Phase 1 (parallel):
T002 — create batch_check.py stub
T003 — create test file stub

# Phase 2 (sequential - each schema depends on previous for imports):
T004 → T005 → T006 → T007

# Phase 6 (parallel):
T021 — security fix in geocoding_service.py
T022 — integration tests in test_voters.py
T023 — unit test for security fix
# T024 requires T012 (route) to be done, but can run parallel to T021/T023
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (stubs)
2. Complete Phase 2: Foundational (schemas) — CRITICAL
3. Complete Phase 3: User Story 1 (library + service + route + unit tests)
4. **STOP and VALIDATE**: `uv run pytest tests/unit/lib/test_analyzer/test_batch_check.py` — all passing
5. Test manually: start server, call endpoint with admin token
6. Continue to Phase 4 (US2) and Phase 5 (US3) for edge case hardening

### Incremental Delivery

1. Phase 1 + 2 → Schemas defined, stubs created
2. Phase 3 → Core endpoint working (US1)
3. Phase 4 + 5 → Edge cases handled (US2 + US3)
4. Phase 6 → Integration + E2E tests + security fix
5. Phase 7 → Lint, coverage, commit

---

## Notes

- All 3 user stories share one endpoint — implementation is sequential by necessity (same library function)
- The CROSS JOIN approach requires `boundary_ids` to be fetched first (separate query), then used in the cross-join `IN` clause — two queries total for the happy path
- The `VoterNotFoundError` exception should live in `batch_check.py` (or a shared exceptions module if one exists)
- No Alembic migration is required — zero schema changes
- Georgia validation fix is a one-liner addition to an existing service function — no new dependencies
