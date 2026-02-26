# Tasks: Election Information

**Input**: Design documents from `/specs/010-election-info/`
**Prerequisites**: plan.md, spec.md, data-model.md, contracts/openapi.yaml, research.md

**Tests**: Included — constitution principle III (Testing Discipline) requires 90% coverage and tests for all new code.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Database + Models + Schemas)

**Purpose**: Migrations, ORM models, and Pydantic schemas that ALL user stories depend on. Must complete before any story work begins.

- [X] T001 [P] Create Alembic migration for candidates and candidate_links tables in alembic/versions/037_add_candidates.py per data-model.md schema (candidates: UUID PK, election_id FK CASCADE, full_name, party, bio, photo_url, ballot_order, filing_status with CHECK, is_incumbent, sos_ballot_option_id, timestamps; candidate_links: UUID PK, candidate_id FK CASCADE, link_type with CHECK, url, label, created_at; indexes: ix_candidates_election_id, ix_candidates_filing_status, ix_candidates_sos_ballot_option_id partial, ix_candidate_links_candidate_id; unique: uq_candidate_election_name)
- [X] T002 [P] Create Alembic migration to add 9 nullable metadata columns to elections table in alembic/versions/038_add_election_metadata.py (description TEXT, purpose TEXT, eligibility_description TEXT, registration_deadline DATE, early_voting_start DATE, early_voting_end DATE, absentee_request_deadline DATE, qualifying_start TIMESTAMPTZ, qualifying_end TIMESTAMPTZ)
- [X] T003 [P] Create Candidate and CandidateLink ORM models in src/voter_api/models/candidate.py (Candidate: Base+UUIDMixin+TimestampMixin, all columns per data-model.md, links relationship with lazy="selectin" and cascade="all, delete-orphan"; CandidateLink: Base+UUIDMixin, candidate_id FK, link_type, url, label, created_at; both with __table_args__ for constraints and indexes)
- [X] T004 [P] Add 9 new nullable metadata columns and candidates relationship to Election model in src/voter_api/models/election.py (description, purpose, eligibility_description as Text nullable; registration_deadline, early_voting_start, early_voting_end, absentee_request_deadline as Date nullable; qualifying_start, qualifying_end as DateTime(timezone=True) nullable; candidates relationship to Candidate with cascade="all, delete-orphan")
- [X] T005 Register Candidate and CandidateLink models in src/voter_api/models/__init__.py
- [X] T006 [P] Create candidate Pydantic schemas in src/voter_api/schemas/candidate.py (CandidateLinkResponse, CandidateLinkCreateRequest with link_type enum validator, CandidateSummaryResponse with model_config from_attributes, CandidateDetailResponse extending Summary with bio/links/sos_ballot_option_id/result_vote_count/result_political_party/updated_at, PaginatedCandidateResponse, CandidateCreateRequest with full_name required and optional links array, CandidateUpdateRequest for PATCH with all fields optional EXCEPT full_name which must be str not str|None to prevent null on NOT NULL column, FilingStatus and LinkType string enums)
- [X] T007 [P] Extend election schemas in src/voter_api/schemas/election.py (add 9 new optional fields to ElectionUpdateRequest: description, purpose, eligibility_description, registration_deadline, early_voting_start, early_voting_end, absentee_request_deadline, qualifying_start, qualifying_end; add same 9 nullable fields to ElectionSummary and ElectionDetailResponse for backward-compatible response enrichment)

**Checkpoint**: Foundation ready — all models, schemas, and migrations in place. User story implementation can begin.

---

## Phase 2: User Story 1 — Browse Candidates Before Election Day (Priority: P1) MVP

**Goal**: Voters can view a paginated list of candidates for any election and see individual candidate detail with profile info and links. Public read-only access.

**Independent Test**: Create an election, add candidates via DB seed, retrieve candidate list and detail via public API — all profile fields returned.

### Implementation for User Story 1

- [X] T008 [US1] Implement list_candidates and get_candidate functions in src/voter_api/services/candidate_service.py (list_candidates: accepts session, election_id, optional status filter, page, page_size; returns tuple[list[Candidate], int] using count+paginated query pattern; get_candidate: accepts session, candidate_id; returns Candidate|None; both use selectinload for links)
- [X] T009 [US1] Implement GET /elections/{election_id}/candidates route in src/voter_api/api/v1/candidates.py (public, paginated, optional status filter param, validates election exists with 404, returns PaginatedCandidateResponse; follow route ordering: fixed paths before parameterized)
- [X] T010 [US1] Implement GET /candidates/{candidate_id} route in src/voter_api/api/v1/candidates.py (public, returns CandidateDetailResponse with links, 404 if not found)
- [X] T011 [US1] Register candidates router in src/voter_api/main.py (include router with prefix="/api/v1" and appropriate tags)

### Tests for User Story 1

- [X] T012 [P] [US1] Write unit tests for candidate schemas in tests/unit/test_candidate_schemas.py (CandidateCreateRequest: required full_name validation, optional fields default values, filing_status enum validation, link_type enum validation; CandidateSummaryResponse: from_attributes ORM mapping; CandidateUpdateRequest: all-optional partial validation; CandidateLinkCreateRequest: required fields, link_type enum)
- [X] T013 [P] [US1] Write integration tests for candidate list and detail API in tests/integration/test_candidate_api.py (GET list: empty election returns empty list, populated election returns candidates with pagination, status filter works, 404 for nonexistent election; GET detail: returns full profile with links, 404 for nonexistent candidate)

**Checkpoint**: User Story 1 complete — voters can browse candidates for any election via public API.

---

## Phase 3: User Story 2 — View Election Details and Purpose (Priority: P2)

**Goal**: Election detail responses include enriched metadata (description, purpose, eligibility, milestone dates) alongside existing fields. Fully backward compatible.

**Independent Test**: Create an election via existing endpoint, PATCH with metadata fields, verify GET detail returns all new fields. Verify election without metadata still returns correctly with null fields.

### Implementation for User Story 2

No code changes needed — the existing GET /elections/{id} route already returns `ElectionDetailResponse`, which now includes the new metadata fields via the schema extension in T007. Verification is handled entirely by the test below.

### Tests for User Story 2

- [X] T014 [US2] Write integration tests for election metadata in detail response in tests/integration/test_election_metadata_api.py (GET election detail: returns new metadata fields when populated, returns null for metadata fields when not set, backward compatible with existing response consumers; also verifies schema extension from T007 is wired correctly end-to-end)

**Checkpoint**: User Story 2 complete — election detail includes enriched metadata when populated.

---

## Phase 4: User Story 3 — Administer Candidate and Election Data (Priority: P2)

**Goal**: Admins can perform full CRUD on candidates (create, update, delete, manage links) and enrich elections with metadata. RBAC enforced.

**Independent Test**: Authenticate as admin, create candidate with links, update filing status, delete candidate, update election metadata — all via API. Verify non-admin gets 403.

### Implementation for User Story 3

- [X] T016 [US3] Implement create_candidate function in src/voter_api/services/candidate_service.py (validates election exists, creates Candidate + initial CandidateLink entries from request.links, handles IntegrityError for duplicate name → ValueError, flush before commit to get ID for links)
- [X] T017 [US3] Implement update_candidate and delete_candidate functions in src/voter_api/services/candidate_service.py (update: _UPDATABLE_FIELDS frozenset allowlist pattern, model_dump(exclude_unset=True), IntegrityError → ValueError for name conflict; delete: session.delete with cascade)
- [X] T018 [US3] Implement add_candidate_link and delete_candidate_link functions in src/voter_api/services/candidate_service.py (add: validates candidate exists, creates CandidateLink; delete: validates both candidate and link exist and link belongs to candidate, 404 if not)
- [X] T019 [US3] Implement POST /elections/{election_id}/candidates route in src/voter_api/api/v1/candidates.py (admin-only via require_role("admin"), validates election exists 404, calls create_candidate, returns 201 with CandidateDetailResponse, catches ValueError → 409)
- [X] T020 [US3] Implement PATCH /candidates/{candidate_id} route in src/voter_api/api/v1/candidates.py (admin-only, 404 if not found, calls update_candidate with model_dump(exclude_unset=True), catches ValueError → 409, returns CandidateDetailResponse)
- [X] T021 [US3] Implement DELETE /candidates/{candidate_id} route in src/voter_api/api/v1/candidates.py (admin-only, 404 if not found, calls delete_candidate, returns 204 No Content)
- [X] T022 [P] [US3] Implement POST /candidates/{candidate_id}/links and DELETE /candidates/{candidate_id}/links/{link_id} routes in src/voter_api/api/v1/candidates.py (both admin-only; POST: validates candidate exists 404, returns 201 with CandidateLinkResponse; DELETE: validates candidate and link exist 404, returns 204)
- [X] T023 [US3] Verify election metadata update works in existing PATCH /elections/{id} — the existing update_election service function in src/voter_api/services/election_service.py uses model_dump(exclude_unset=True) + setattr() with no allowlist, so new fields from ElectionUpdateRequest schema extension (T007) are handled automatically with no service code changes needed; verify via integration test only

### Tests for User Story 3

- [X] T024 [P] [US3] Write integration tests for candidate CRUD and RBAC in tests/integration/test_candidate_api.py (POST create: happy path 201, duplicate name 409, nonexistent election 404, non-admin 403, 401 without auth; PATCH update: happy path, status change to withdrawn, 404, 403; DELETE: happy path 204, 404, 403; link add: 201, 404 candidate; link delete: 204, 404)
- [X] T025 [P] [US3] Write integration tests for candidate service layer in tests/integration/test_candidate_service.py (create_candidate: with links, without links, duplicate IntegrityError; update_candidate: partial update, allowlist enforcement; delete_candidate: cascade removes links; list_candidates: pagination, status filter, election_id filter)
- [X] T026 [P] [US3] Write integration tests for election metadata update in tests/integration/test_election_metadata_api.py (PATCH election with description/purpose/milestone dates, verify fields persisted and returned in detail, verify backward compat with no metadata)

**Checkpoint**: User Story 3 complete — admins can fully manage candidates and election metadata.

---

## Phase 5: User Story 4 — Find Elections by Eligibility and Geography (Priority: P3)

**Goal**: Election list endpoint supports filtering by milestone dates (registration_open, early_voting_active) and geography (district_type, district_identifier).

**Independent Test**: Create elections with varying milestone dates and districts, filter via new query params, verify correct results returned.

### Implementation for User Story 4

- [X] T027 [US4] Add registration_open, early_voting_active, district_type, and district_identifier query parameters to GET /elections list endpoint in src/voter_api/api/v1/elections.py (registration_open: bool filter → WHERE registration_deadline >= CURRENT_DATE; early_voting_active: bool filter → WHERE early_voting_start <= CURRENT_DATE AND early_voting_end >= CURRENT_DATE; district_type/district_identifier: exact match filters on existing parsed columns)
- [X] T028 [US4] Update election list service function in src/voter_api/services/election_service.py to accept and apply the 4 new filter parameters (add to both count query and paginated query; use func.current_date() for date comparisons)

### Tests for User Story 4

- [X] T029 [US4] Write integration tests for election milestone date and geography filters in tests/integration/test_election_metadata_api.py (registration_open=true returns only elections with future deadline, early_voting_active=true returns only elections in window, district_type+district_identifier filters correctly, combined filters work)

**Checkpoint**: User Story 4 complete — voters can find elections by eligibility criteria and geography.

---

## Phase 6: User Story 5 — Cross-Reference Candidates with Election Results (Priority: P3)

**Goal**: Candidate detail response includes SOS result data (vote count) when sos_ballot_option_id matches an entry in the election's results_data JSONB.

**Independent Test**: Create candidate with sos_ballot_option_id, seed election results with matching ID, verify candidate detail includes vote count.

### Implementation for User Story 5

- [X] T030 [US5] Enrich candidate detail response with SOS result data in src/voter_api/services/candidate_service.py (when returning a candidate with sos_ballot_option_id set, query the election's result.results_data JSONB for a matching ballot option ID, extract vote_count and political_party from the match, populate the result_vote_count and result_political_party fields already defined on CandidateDetailResponse by T006)

### Tests for User Story 5

- [X] T032 [US5] Write integration tests for SOS results cross-reference in tests/integration/test_candidate_api.py (candidate with matching sos_ballot_option_id returns vote_count from results, candidate without match returns null fields, candidate with no sos_ballot_option_id returns null fields)

**Checkpoint**: User Story 5 complete — candidates show result data when available.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: E2E tests, lint, coverage, and final validation across all stories.

- [X] T033 Add candidate and candidate_link seed data to E2E test fixtures in tests/e2e/conftest.py (add CANDIDATE_ID and CANDIDATE_LINK_ID UUID constants, insert candidate row for seeded election with a link, use on_conflict_do_update for idempotency, add cleanup DELETEs in reverse FK order)
- [X] T034 Add TestCandidates E2E smoke test class in tests/e2e/test_smoke.py (list candidates: public 200 with pagination and response time < 2s per SC-002, detail: 200 with links, create: admin 201, update: admin 200, delete: admin 204, link add: admin 201, link delete: admin 204, RBAC: viewer 403 on write ops, 404 for nonexistent candidate)
- [X] T035 Update TestElections E2E smoke tests in tests/e2e/test_smoke.py (verify election detail response includes new metadata fields when populated, verify metadata fields are null for elections without enrichment)
- [X] T036 Run ruff lint and format check across all new and modified files (uv run ruff check . && uv run ruff format --check .; fix any violations)
- [X] T037 Run full test suite with coverage and verify 90% threshold (uv run pytest --cov=voter_api --cov-report=term-missing; fix any coverage gaps in new code)
- [X] T038 Run E2E test collection check (uv run pytest tests/e2e/ --collect-only to verify all new tests are discoverable)
- [X] T039 [P] Write contract tests in tests/contract/test_candidate_contract.py verifying candidate API responses match the OpenAPI spec in specs/010-election-info/contracts/openapi.yaml (required fields present, field types match, enum values valid, pagination shape correct; per constitution Principle III requiring contract/ test directory)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on Phase 1 completion (needs models + schemas)
- **US2 (Phase 3)**: Depends on Phase 1 completion (needs election schema extension)
- **US3 (Phase 4)**: Depends on Phase 1 + Phase 2 (needs read endpoints before write endpoints)
- **US4 (Phase 5)**: Depends on Phase 1 (needs election metadata columns)
- **US5 (Phase 6)**: Depends on Phase 2 (needs candidate model + detail endpoint)
- **Polish (Phase 7)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Foundation only — independently testable as MVP
- **US2 (P2)**: Foundation only — independently testable (only needs election metadata columns)
- **US3 (P2)**: Depends on US1 (candidate read endpoints must exist before write endpoints make sense)
- **US4 (P3)**: Foundation only — independently testable (only needs election list endpoint changes)
- **US5 (P3)**: Depends on US1 (needs candidate detail endpoint to enrich)

### Within Each User Story

- Models before services
- Services before routes
- Routes before tests (tests verify routes work)
- Core implementation before integration

### Parallel Opportunities

- **Phase 1**: T001, T002, T003, T004 can all run in parallel (different files)
- **Phase 1**: T006 and T007 can run in parallel (different schema files)
- **Phase 2**: US1 and US2 can start in parallel after Phase 1
- **Phase 4**: T024, T025, T026 test tasks can run in parallel
- **Phase 7**: T033, T034, T035 can run in parallel (different test sections)

---

## Parallel Example: Phase 1 (Foundational)

```bash
# Launch all migrations and models together:
Task: "Create migration 037_add_candidates.py"
Task: "Create migration 038_add_election_metadata.py"
Task: "Create Candidate ORM models in models/candidate.py"
Task: "Add metadata columns to Election model in models/election.py"

# Then launch schemas together:
Task: "Create candidate schemas in schemas/candidate.py"
Task: "Extend election schemas in schemas/election.py"
```

## Parallel Example: User Story 1

```bash
# Launch tests and service in parallel:
Task: "Unit tests for candidate schemas"
Task: "Implement list_candidates and get_candidate service functions"

# Then routes (depend on service):
Task: "GET /elections/{election_id}/candidates route"
Task: "GET /candidates/{candidate_id} route"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (migrations + models + schemas)
2. Complete Phase 2: User Story 1 (list + detail endpoints + tests)
3. **STOP and VALIDATE**: Test candidate browsing independently
4. Deploy/demo if ready — voters can browse candidates

### Incremental Delivery

1. Phase 1 (Foundational) → Foundation ready
2. US1 (Browse Candidates) → Test → Deploy (MVP)
3. US2 (Election Details) + US3 (Admin CRUD) → Test → Deploy
4. US4 (Filters) + US5 (Results Cross-Reference) → Test → Deploy
5. Phase 7 (Polish + E2E) → Final validation

### Recommended Execution Order (Single Developer)

Phase 1 → US1 → US3 → US2 → US4 → US5 → Polish

Rationale: US3 (admin CRUD) immediately after US1 (read) gives a complete candidate management workflow. US2 (election metadata) is a quick win after the candidate foundation is in place. US4 and US5 are independent enhancements.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each phase or logical group
- Stop at any checkpoint to validate story independently
- Constitution requires: type hints, Google-style docstrings, ruff pass, 90% coverage
