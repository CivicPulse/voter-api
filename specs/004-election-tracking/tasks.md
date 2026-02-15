# Tasks: Election Result Tracking

**Input**: Design documents from `/specs/004-election-tracking/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/openapi.yaml

**Tests**: Inline with each phase — constitution mandates 90% coverage before every commit. Unit tests follow library implementation; integration tests follow each user story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Extend existing project configuration for election tracking feature

- [ ] T001 Add `ELECTION_REFRESH_ENABLED` and `ELECTION_REFRESH_INTERVAL` settings to `src/voter_api/core/config.py`
- [ ] T002 [P] Add election refresh environment variables to `.env.example`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data layer and standalone library that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Create Election, ElectionResult, and ElectionCountyResult ORM models in `src/voter_api/models/election.py` (UUIDMixin, TimestampMixin, JSONB columns, relationships, constraints per data-model.md)
- [ ] T004 Create Alembic migration `alembic/versions/015_election_tracking.py` for elections, election_results, and election_county_results tables with indexes and constraints per data-model.md
- [ ] T005 [P] Implement SoS feed Pydantic validation models and `parse_sos_feed()` function in `src/voter_api/lib/election_tracker/parser.py` (models for BallotOption, GroupResult, BallotItem, LocalResult, SoSFeed; parse + validate raw JSON)
- [ ] T006 [P] Implement httpx-based SoS feed HTTP client in `src/voter_api/lib/election_tracker/fetcher.py` (async fetch_election_results(url) returning parsed SoSFeed, typed error handling, timeout config; follow CensusGeocoder pattern)
- [ ] T007 Implement result upsert logic in `src/voter_api/lib/election_tracker/ingester.py` (upsert statewide election_results row, upsert per-county election_county_results rows with county_name_normalized stripping " County" suffix, accept parsed SoSFeed + AsyncSession)
- [ ] T008 [P] Create public API exports in `src/voter_api/lib/election_tracker/__init__.py` (export parse_sos_feed, fetch_election_results, ingest_election_results, SoSFeed, FetchError)
- [ ] T009 Create Pydantic v2 request/response schemas in `src/voter_api/schemas/election.py` (ElectionCreateRequest, ElectionUpdateRequest, ElectionSummary, ElectionDetailResponse, PaginationMeta, PaginatedElectionListResponse, CandidateResult, VoteMethodResult, CountyResultSummary, ElectionResultsResponse, ElectionResultFeature, ElectionResultFeatureCollection, RefreshResponse per contracts/openapi.yaml)
- [ ] T010 [P] Register election models in `src/voter_api/models/__init__.py` (import Election, ElectionResult, ElectionCountyResult so Alembic autogenerate discovers them)
- [ ] T010a [P] Write unit tests for SoS feed parser in `tests/unit/lib/test_election_tracker/test_parser.py` (valid feed parsing, malformed JSON rejection, missing fields, candidate list changes)
- [ ] T010b [P] Write unit tests for SoS feed fetcher in `tests/unit/lib/test_election_tracker/test_fetcher.py` (successful fetch, timeout handling, HTTP error codes, invalid response body; mock httpx)
- [ ] T010c [P] Write unit tests for result ingester in `tests/unit/lib/test_election_tracker/test_ingester.py` (statewide upsert, county upsert with name normalization, re-ingest replaces existing data, county_name_normalized strips " County" suffix)

**Checkpoint**: Foundation ready — ORM models, migration, library modules, schemas, and unit tests are in place. User story implementation can now begin.

---

## Phase 3: User Story 1 — View Live Election Results (Priority: P1) MVP

**Goal**: Public users can retrieve statewide and county-level election results as JSON with candidate vote counts, precinct reporting status, and vote method breakdowns.

**Independent Test**: Create an election via service layer, ingest results using the library, then GET `/api/v1/elections/{id}/results` and verify the JSON response contains candidates, votes, precincts, and vote method breakdowns. Also GET `/api/v1/elections/{id}` for election metadata.

### Implementation for User Story 1

- [ ] T011 [US1] Implement core election service methods in `src/voter_api/services/election_service.py` (create_election, get_election_by_id, get_election_results assembling statewide + county data from ORM into response schemas, refresh_single_election orchestrating fetch→parse→ingest pipeline, update election last_refreshed_at)
- [ ] T012 [US1] Implement GET `/elections/{election_id}` route handler in `src/voter_api/api/v1/elections.py` (public, returns ElectionDetailResponse, 404 if not found)
- [ ] T013 [US1] Implement GET `/elections/{election_id}/results` route handler in `src/voter_api/api/v1/elections.py` (public, returns ElectionResultsResponse with statewide candidates + county_results array, includes last_refreshed_at, status-dependent Cache-Control header: 60s active / 86400s finalized, 404 if not found)
- [ ] T014 [US1] Create election router and wire into main API router in `src/voter_api/api/v1/elections.py` and `src/voter_api/api/router.py` (add elections_router with `/elections` prefix to create_router function)
- [ ] T014a [US1] Write integration tests for US1 endpoints in `tests/integration/test_election_api.py` (GET /elections/{id}, GET /elections/{id}/results, Cache-Control headers, 404 handling, last_refreshed_at presence)

**Checkpoint**: User Story 1 is fully functional and tested — election results are accessible via JSON API with cache headers. MVP is deliverable.

---

## Phase 4: User Story 2 — View Election Results on a Map (Priority: P2)

**Goal**: Public users can retrieve election results as GeoJSON FeatureCollection with county boundary geometries for map rendering.

**Independent Test**: GET `/api/v1/elections/{id}/results/geojson` for an election with ingested results and verify the response is a valid GeoJSON FeatureCollection where each Feature has a county boundary geometry and result properties. Counties without results should still appear with null values.

### Implementation for User Story 2

- [ ] T015 [US2] Implement GeoJSON generation method in `src/voter_api/services/election_service.py` (get_election_results_geojson: query election_county_results joined to county_metadata.name → boundaries.geometry via GEOID, build ElectionResultFeatureCollection with ST_AsGeoJSON, include election metadata (election_id, election_name, election_date, status, last_refreshed_at) as top-level FeatureCollection properties per FR-012, include counties with no results as null-value features)
- [ ] T016 [US2] Implement GET `/elections/{election_id}/results/geojson` route handler in `src/voter_api/api/v1/elections.py` (public, returns ElectionResultFeatureCollection with content-type `application/geo+json`, status-dependent Cache-Control header, 404 if not found)
- [ ] T016a [US2] Write integration tests for GeoJSON endpoint in `tests/integration/test_election_api.py` (GET /elections/{id}/results/geojson, valid FeatureCollection structure, content-type application/geo+json, election metadata in top-level properties, counties with null results included, Cache-Control headers)

**Checkpoint**: User Stories 1 AND 2 are independently functional and tested — JSON and GeoJSON result endpoints work.

---

## Phase 5: User Story 3 — Automatic Result Refresh (Priority: P2)

**Goal**: Active elections have their results automatically refreshed from SoS data feeds on a configurable interval, and a CLI command enables manual/cron-triggered refresh.

**Independent Test**: Configure an election with a data source URL, start the background refresh loop (or run CLI refresh), and verify stored results are updated. Verify finalized elections are skipped. Verify data source failures are logged without crashing.

### Implementation for User Story 3

- [ ] T017 [US3] Implement background refresh loop function in `src/voter_api/services/election_service.py` (refresh_all_active_elections: query active elections, fetch+parse+ingest each, log errors per-election without stopping, respect ELECTION_REFRESH_INTERVAL; election_refresh_loop: asyncio while-loop calling refresh_all_active_elections on interval)
- [ ] T018 [US3] Integrate background refresh into FastAPI lifespan in `src/voter_api/main.py` (if ELECTION_REFRESH_ENABLED, create asyncio task for election_refresh_loop in lifespan startup, cancel on shutdown)
- [ ] T019 [US3] Implement Typer CLI `election refresh` command in `src/voter_api/cli/election_cmd.py` (refresh single election by ID or all active elections, register with main CLI app; uses election_service.refresh_single_election / refresh_all_active_elections)
- [ ] T019a [US3] Write integration tests for CLI refresh command in `tests/integration/test_election_cli.py` (refresh single election, refresh all active, skip finalized, handle data source failure gracefully)

**Checkpoint**: Automatic refresh and CLI manual refresh are operational and tested. Active elections stay current without manual intervention.

---

## Phase 6: User Story 4 — Admin Creates and Manages Elections (Priority: P3)

**Goal**: Authenticated admin users can create new elections, update election metadata, trigger manual refreshes, and finalize elections via API endpoints.

**Independent Test**: Authenticate as admin, POST `/api/v1/elections` to create, PATCH to update, POST `/refresh` to trigger manual refresh. Verify 403 for non-admin users. Verify 409 for duplicate name+date.

### Implementation for User Story 4

- [ ] T020 [US4] Implement POST `/elections` route handler in `src/voter_api/api/v1/elections.py` (admin-only via require_role("admin"), validate ElectionCreateRequest, call election_service.create_election, return 201 ElectionDetailResponse, 409 on duplicate name+date, 401/403 for auth failures)
- [ ] T021 [US4] Implement PATCH `/elections/{election_id}` route handler in `src/voter_api/api/v1/elections.py` (admin-only, partial update via ElectionUpdateRequest, call election_service.update_election, return ElectionDetailResponse, 404 if not found)
- [ ] T022 [US4] Implement POST `/elections/{election_id}/refresh` route handler in `src/voter_api/api/v1/elections.py` (admin-only, call election_service.refresh_single_election, return RefreshResponse with refreshed_at + counties_updated + precinct counts, 404 if not found, 502 on data source failure)
- [ ] T022a [US4] Write integration tests for admin endpoints in `tests/integration/test_election_api.py` (POST create 201, PATCH update, POST refresh, auth enforcement 401/403 for non-admin, duplicate 409, source failure 502)

**Checkpoint**: Full admin CRUD and manual refresh via API are tested. Non-admin access is denied.

---

## Phase 7: User Story 5 — List and Filter Elections (Priority: P3)

**Goal**: Public users can browse and filter elections by status, election type, and date range with paginated results.

**Independent Test**: Create multiple elections with different statuses/types/dates, GET `/api/v1/elections` with various filter combinations, verify correct filtering and pagination metadata.

### Implementation for User Story 5

- [ ] T023 [US5] Implement list_elections service method in `src/voter_api/services/election_service.py` (paginated query with optional filters: status, election_type, district, date_from, date_to; district filter uses case-insensitive partial match; order by election_date DESC; return PaginatedElectionListResponse with ElectionSummary items including precincts_reporting/participating from joined election_results)
- [ ] T024 [US5] Implement GET `/elections` route handler in `src/voter_api/api/v1/elections.py` (public, query params for status/election_type/district/date_from/date_to/page/page_size per openapi.yaml, return PaginatedElectionListResponse)
- [ ] T024a [US5] Write integration tests for list/filter endpoint in `tests/integration/test_election_api.py` (pagination, status filter, date range filter, election_type filter, district partial match)

**Checkpoint**: All 5 user stories are independently functional and tested. Full election tracking system is operational.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Contract tests, lint validation, and integration verification across all user stories

- [ ] T025 [P] Write OpenAPI contract tests in `tests/contract/test_election_contract.py` (validate all 7 endpoint response schemas match contracts/openapi.yaml definitions)
- [ ] T026 Run ruff check and ruff format on all new files, fix any violations
- [ ] T027 Validate quickstart.md scenarios against running API (create election, refresh, view results, view GeoJSON)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (Phase 3) should be completed first as the MVP
  - US2 (Phase 4) and US3 (Phase 5) can proceed in parallel after US1
  - US4 (Phase 6) and US5 (Phase 7) can proceed in parallel after US1
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) — No dependencies on other stories. **This is the MVP.**
- **User Story 2 (P2)**: Can start after US1 (reuses election_service and result data patterns)
- **User Story 3 (P2)**: Can start after US1 (reuses refresh_single_election from service layer)
- **User Story 4 (P3)**: Can start after Foundational — admin endpoints are independent of public result endpoints but practically benefit from US1's service layer
- **User Story 5 (P3)**: Can start after Foundational — list endpoint is independent

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Story complete before moving to next priority
- Commit after each task or logical group

### Parallel Opportunities

- **Phase 1**: T001 and T002 can run in parallel
- **Phase 2**: T005, T006, T008, T010 can run in parallel (different files). T007 depends on T005 (uses parser types). T009 can run parallel to library tasks. T004 depends on T003 (migration references models).
- **Phase 3**: T012, T013 can run in parallel once T011 (service) is complete. T014 wires them together.
- **Phase 4**: T015 then T016 (sequential — service before endpoint)
- **Phase 5**: T017 → T018 (sequential). T019 can run parallel to T018.
- **Phase 6**: T020, T021, T022 can all run in parallel (different route handlers, same file but independent functions)
- **Phase 7**: T023 → T024 (sequential — service before endpoint)
- **Phase 2 tests**: T010a, T010b, T010c can all run in parallel (different test files)
- **Phase 8**: T025 can run in parallel with T026; T027 requires running API

---

## Parallel Example: Foundational Phase

```bash
# Launch parallel library modules (different files, no dependencies):
Task: "Implement parser in src/voter_api/lib/election_tracker/parser.py"          # T005
Task: "Implement fetcher in src/voter_api/lib/election_tracker/fetcher.py"        # T006
Task: "Create __init__.py in src/voter_api/lib/election_tracker/__init__.py"      # T008
Task: "Register models in src/voter_api/models/__init__.py"                       # T010

# Then sequential (depends on parser types):
Task: "Implement ingester in src/voter_api/lib/election_tracker/ingester.py"      # T007
```

## Parallel Example: Foundational Phase Tests

```bash
# Launch all unit test files in parallel (after Phase 2 implementation):
Task: "Unit tests for parser in tests/unit/lib/test_election_tracker/test_parser.py"      # T010a
Task: "Unit tests for fetcher in tests/unit/lib/test_election_tracker/test_fetcher.py"    # T010b
Task: "Unit tests for ingester in tests/unit/lib/test_election_tracker/test_ingester.py"  # T010c
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T010)
3. Complete Phase 3: User Story 1 (T011-T014)
4. **STOP and VALIDATE**: Create an election via service/CLI, ingest results, verify GET `/elections/{id}/results` returns correct JSON
5. Deploy/demo if ready — public users can view live election results

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (**MVP!**)
3. Add User Story 2 (GeoJSON) → Test independently → Deploy/Demo
4. Add User Story 3 (Auto-refresh) → Test independently → Deploy/Demo
5. Add User Story 4 (Admin CRUD) → Test independently → Deploy/Demo
6. Add User Story 5 (List/Filter) → Test independently → Deploy/Demo
7. Complete Polish → Full test coverage, lint clean, contract validated

### Recommended Single-Developer Order

Since this is a single-developer project:

1. **Phase 1 + 2**: Setup, foundation, and unit tests (T001-T010, T010a-T010c)
2. **Phase 3**: US1 MVP — view results + integration tests (T011-T014, T014a)
3. **Phase 6**: US4 admin CRUD + integration tests (T020-T022, T022a)
4. **Phase 5**: US3 auto-refresh + CLI tests (T017-T019, T019a)
5. **Phase 4**: US2 GeoJSON + integration tests (T015-T016, T016a)
6. **Phase 7**: US5 list/filter + integration tests (T023-T024, T024a)
7. **Phase 8**: Polish — contract tests, lint, validation (T025-T027)

This order prioritizes getting a working end-to-end flow (create election → ingest → view results) before adding visualization and automation.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- No new dependencies needed — all libraries (httpx, SQLAlchemy, GeoAlchemy2, etc.) already in pyproject.toml
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
