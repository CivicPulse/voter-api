# Tasks: Election Lifecycle Management

**Input**: Design documents from `specs/012-election-lifecycle/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi-patch.yaml, quickstart.md

**Feature Branch**: `012-election-lifecycle`
**Generated**: 2026-02-26

**Organization**: Tasks are grouped by implementation phase and user story. The foundational phase (migration + model + schema) must complete before any user story work begins. User stories US1 (soft-delete) and US2 (manual creation) can be worked independently after the foundation. US3 (link to feed) depends on US2. US4 (source filter) depends on US1 and US2 for test data but is implemented alongside the service layer.

---

## Phase 1: Foundational — Migration, Model, and Schemas

**Purpose**: Schema changes that all four user stories depend on. No user story work can begin until this phase is complete.

**Why blocking**: The `deleted_at`, `source`, and nullable `data_source_url` columns must exist in the database and ORM before any service or router code can reference them.

- [x] T001 Write Alembic migration `alembic/versions/039_election_lifecycle.py` — add `deleted_at` (TIMESTAMPTZ nullable, index `idx_elections_deleted_at`), add `source` (VARCHAR(20) NOT NULL server_default `sos_feed`, check constraint `ck_election_source`, index `idx_elections_source`), and alter `data_source_url` to nullable; include full `downgrade()` in reverse order. **Confirm**: migration must NOT add `ON DELETE CASCADE` on the `voter_history.election_id` FK — voter history records must survive election soft-delete (FR-003, FR-012)
- [x] T002 Update `Election` ORM model in `src/voter_api/models/election.py` — add `SoftDeleteMixin` to class bases (import from `voter_api.models.base`), add `source: Mapped[str]` column with `server_default="sos_feed"`, change `data_source_url: Mapped[str | None]` (nullable=True), add `CheckConstraint` for `ck_election_source` and `Index` for `idx_elections_source` to `__table_args__`
- [x] T003 [P] Add `ElectionLinkRequest` schema to `src/voter_api/schemas/election.py` — new `BaseModel` with required `data_source_url: HttpUrl` and optional `ballot_item_id: str | None`
- [x] T004 [P] Update `ElectionCreateRequest` in `src/voter_api/schemas/election.py` — add required `source: Literal["sos_feed", "manual"]` field, change `data_source_url` to `HttpUrl | None = None`, add `boundary_id: uuid.UUID | None = None`, add `@model_validator(mode="after")` enforcing source-specific field requirements
- [x] T005 [P] Update `ElectionSummary` and `ElectionDetailResponse` in `src/voter_api/schemas/election.py` — add `source: str` field to both, change `data_source_url` type to `str | None` in `ElectionDetailResponse`
- [x] T006 Verify migration applies cleanly: run `uv run alembic upgrade head` and confirm `uv run pytest tests/e2e/ --collect-only` still discovers all existing tests

**Checkpoint**: Foundation ready — migration applied, ORM updated, schemas updated. All four user stories can now proceed.

---

## Phase 2: User Story 1 — Soft-Delete an Election (Priority: P1)

**Goal**: Administrators can soft-delete an election by setting `deleted_at`; the election disappears from all list and detail responses immediately. Voter history is preserved.

**Independent Test**: Create an election, call `DELETE /api/v1/elections/{id}` as admin (expect 204), call `GET /api/v1/elections/{id}` (expect 404), confirm voter history records referencing the election still exist.

### Tests for User Story 1

- [x] T007 [P] [US1] Write unit tests in `tests/unit/services/test_election_lifecycle.py` covering: `test_soft_delete_election_marks_deleted_at`, `test_soft_delete_election_returns_false_if_not_found`, `test_get_election_by_id_excludes_deleted`, `test_list_elections_excludes_deleted`
- [x] T008 [P] [US1] Write integration tests in `tests/integration/api/test_elections_lifecycle.py` covering: `test_delete_election_admin_returns_204`, `test_delete_election_viewer_returns_403`, `test_delete_election_unauthenticated_returns_401`, `test_delete_election_not_found_returns_404`, `test_delete_election_already_deleted_returns_404`, `test_deleted_election_not_in_list`, `test_deleted_election_detail_returns_404`, `test_voter_history_preserved_after_election_soft_delete` (seed a voter_history record referencing a test election, soft-delete the election, then query voter_history by that election_id directly via the DB and assert the record still exists — verifies FR-003 and FR-012)

### Implementation for User Story 1

- [x] T009 [US1] Add `Election.deleted_at.is_(None)` filter to `get_election_by_id`, `list_elections`, and `refresh_all_active_elections` in `src/voter_api/services/election_service.py`
- [x] T010 [US1] Add `soft_delete_election(session, election_id) -> bool` function to `src/voter_api/services/election_service.py` — fetch via `get_election_by_id` (which now excludes deleted), set `deleted_at = datetime.now(UTC)`, commit, return True; return False if not found
- [x] T011 [US1] Update `build_detail_response` in `src/voter_api/services/election_service.py` to include `source=election.source` and handle nullable `data_source_url`; update `list_elections` summary-building path to include `source` in `ElectionSummary` objects
- [x] T012 [US1] Add `DELETE /{election_id}` endpoint to `src/voter_api/api/v1/elections.py` — status 204, admin-only via `require_role("admin")`, calls `soft_delete_election`, returns 404 if False
- [x] T013 [US1] Run unit and integration tests for soft-delete: `uv run pytest tests/unit/services/test_election_lifecycle.py tests/integration/api/test_elections_lifecycle.py -k "delete or soft_delete or excludes_deleted" -v`

**Checkpoint**: Soft-delete is fully functional. `DELETE /api/v1/elections/{id}` works. Deleted elections are invisible. Voter history intact.

---

## Phase 3: User Story 2 — Create a Manual Election with District Boundary (Priority: P2)

**Goal**: Administrators can create elections with `source="manual"` and a `boundary_id` reference; the system validates the boundary exists and stores the election with `data_source_url=NULL`.

**Independent Test**: Select an existing boundary ID, `POST /api/v1/elections` with `source="manual"` and `boundary_id`, verify 201 response with `source="manual"` and `data_source_url=null`; attempt with a non-existent boundary ID and verify 422.

### Tests for User Story 2

- [x] T014 [P] [US2] Add unit tests to `tests/unit/services/test_election_lifecycle.py` covering: `test_create_election_manual_validates_boundary_required`, `test_create_election_manual_validates_boundary_exists`, `test_create_election_manual_sets_source_manual`, `test_create_election_sos_feed_sets_source_sos_feed`
- [x] T015 [P] [US2] Add integration tests to `tests/integration/api/test_elections_lifecycle.py` covering: `test_create_manual_election_success`, `test_create_manual_election_without_boundary_returns_422`, `test_create_manual_election_invalid_boundary_returns_422`, `test_create_sos_feed_election_without_url_returns_422`

### Implementation for User Story 2

- [x] T016 [US2] Update `create_election` service function in `src/voter_api/services/election_service.py` — accept `source` from request, set `source=request.source` on the `Election` object; for `source="manual"`, validate boundary exists via `session.get(Boundary, request.boundary_id)` (raise ValueError if not found), set `election.boundary_id = request.boundary_id` and skip `link_election_to_boundary`; for `source="sos_feed"`, continue existing behavior
- [x] T017 [US2] Audit all `Election(...)` constructor calls in `src/voter_api/services/election_service.py` (import-feed path: `import_feed`, `_create_or_update_election_from_race`, and any other helpers) and add `source="sos_feed"` wherever missing
- [x] T018 [US2] Add null-guard to `refresh_single_election` (and any other function that makes HTTP requests to `data_source_url`) in `src/voter_api/services/election_service.py` to skip elections where `data_source_url` is None
- [x] T019 [US2] Run unit and integration tests for manual creation: `uv run pytest tests/unit/services/test_election_lifecycle.py tests/integration/api/test_elections_lifecycle.py -k "manual or sos_feed_sets_source" -v`

**Checkpoint**: Manual election creation works. `source="manual"` + `boundary_id` creates an election with `data_source_url=null`. Validation rejects missing or non-existent boundary.

---

## Phase 4: User Story 3 — Link a Manual Election to SOS Feed Data (Priority: P3)

**Goal**: Administrators can link a manual election to a SOS feed URL, transitioning source from `"manual"` to `"linked"`. Only manual elections can be linked; sos_feed and linked elections are rejected with 400.

**Independent Test**: Create a manual election, call `POST /api/v1/elections/{id}/link` with a feed URL, verify 200 response with `source="linked"` and the provided `data_source_url`; attempt to link a sos_feed election and verify 400.

### Tests for User Story 3

- [x] T020 [P] [US3] Add unit tests to `tests/unit/services/test_election_lifecycle.py` covering: `test_link_election_transitions_source_to_linked`, `test_link_election_sets_data_source_url`, `test_link_election_returns_none_if_not_found`, `test_link_election_raises_value_error_if_not_manual`, `test_link_election_raises_duplicate_error_if_feed_conflict`
- [x] T021 [P] [US3] Add integration tests to `tests/integration/api/test_elections_lifecycle.py` covering: `test_link_election_admin_returns_200`, `test_link_election_non_manual_returns_400`, `test_link_election_duplicate_feed_returns_409`, `test_link_election_not_found_returns_404`, `test_link_election_viewer_returns_403`

### Implementation for User Story 3

- [x] T022 [US3] Add `link_election(session, election_id, request) -> Election | None` function to `src/voter_api/services/election_service.py` — fetch election via `get_election_by_id`, return None if not found; raise `ValueError` if `election.source != "manual"`; check for duplicate `data_source_url + ballot_item_id` via SELECT and raise `DuplicateElectionError` if conflict found; set `election.source = "linked"`, `election.data_source_url = str(request.data_source_url)`, optionally set `ballot_item_id`; commit and refresh
- [x] T023 [US3] Add `POST /{election_id}/link` endpoint to `src/voter_api/api/v1/elections.py` — admin-only, accepts `ElectionLinkRequest` body, calls `link_election` service, returns 200 with `ElectionDetailResponse`; maps ValueError → 400, DuplicateElectionError → 409, None → 404; import `ElectionLinkRequest` in the router import block
- [x] T024 [US3] Run unit and integration tests for link: `uv run pytest tests/unit/services/test_election_lifecycle.py tests/integration/api/test_elections_lifecycle.py -k "link" -v`

**Checkpoint**: Link endpoint works. Manual election transitions to linked, feed URL stored, duplicate feed+ballot_item rejected with 409.

---

## Phase 5: User Story 4 — Filter Elections by Source Type (Priority: P4)

**Goal**: Any user can filter the election list by source type using `?source=sos_feed`, `?source=manual`, or `?source=linked`. Empty results for unmatched filters return an empty list, not an error.

**Independent Test**: Ensure elections of each source type exist (seeded data provides sos_feed; manually create manual and linked in tests), filter by each type, verify only matching elections are returned.

### Tests for User Story 4

- [x] T025 [P] [US4] Add integration tests to `tests/integration/api/test_elections_lifecycle.py` covering: `test_list_elections_source_filter_sos_feed`, `test_list_elections_source_filter_manual`, `test_list_elections_source_filter_linked`, `test_list_elections_source_filter_empty_result`

### Implementation for User Story 4

- [x] T026 [US4] Add `source: str | None = None` parameter to `list_elections` service function signature in `src/voter_api/services/election_service.py`; add `if source: filters.append(Election.source == source)` to the filter list
- [x] T027 [US4] Add `source: str | None = Query(default=None, description="Filter by source type (sos_feed, manual, linked)")` query parameter to the `list_elections` route in `src/voter_api/api/v1/elections.py`; pass `source=source` to the service call
- [x] T028 [US4] Run source filter integration tests: `uv run pytest tests/integration/api/test_elections_lifecycle.py -k "source_filter" -v`

**Checkpoint**: Source filter works on all three values. Empty result returns `[]` not an error.

---

## Phase 6: E2E Smoke Tests

**Purpose**: Validate the full stack (real PostGIS + migrations) for all four user stories.

- [x] T029 Add `test_election_soft_delete_admin` to `TestElections` class in `tests/e2e/test_smoke.py` — create an election, delete it (204), confirm GET returns 404
- [x] T030 [P] Add `test_election_source_filter` to `TestElections` class in `tests/e2e/test_smoke.py` — confirm `GET /api/v1/elections?source=sos_feed` returns results using seeded sos_feed election data
- [x] T031 [P] Add `test_election_create_manual` to `TestElections` class in `tests/e2e/test_smoke.py` — create a manual election using the fixed `BOUNDARY_ID` from `conftest.py`, verify 201 and `source="manual"` in response; add cleanup delete to the session teardown block
- [x] T032 Run full E2E suite to confirm no regressions: `DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api JWT_SECRET_KEY=test-secret-key-minimum-32-characters ELECTION_REFRESH_ENABLED=false uv run pytest tests/e2e/ -v`

---

## Phase 7: Polish and Final Validation

**Purpose**: Lint, coverage, and final verification before committing.

- [x] T033 [P] Run `uv run ruff check .` and `uv run ruff format --check .` — fix all violations before any commit
- [x] T034 [P] Run full test suite with coverage: `uv run pytest tests/unit/ tests/integration/ --cov=voter_api --cov-report=term-missing` — confirm coverage remains at or above 90%
- [x] T035 Validate quickstart examples manually against the running dev server: create a manual election, soft-delete it, link a manual election to a feed URL, filter by source type — per `specs/012-election-lifecycle/quickstart.md`
- [x] T036 Commit phase 1 (migration + model): `feat(elections): add soft-delete and source field (migration 039)`
- [x] T037 [P] Commit phase 2 (schemas): `feat(elections): update election schemas for source and optional data_source_url`
- [x] T038 Commit phase 3 (service soft-delete): `feat(elections): add soft-delete service and filter deleted from all queries`
- [x] T039 Commit phase 4 (service manual + link): `feat(elections): add manual election creation and link-to-feed service`
- [x] T040 Commit phase 5 (router): `feat(elections): add DELETE and link endpoints; source filter on list`
- [x] T041 Commit phase 6 (tests): `test(elections): add lifecycle tests for soft-delete, manual creation, and linking`

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Foundation)**: No dependencies — start immediately
- **Phase 2 (US1 soft-delete)**: Depends on Phase 1 completion
- **Phase 3 (US2 manual creation)**: Depends on Phase 1 completion; can run in parallel with Phase 2
- **Phase 4 (US3 link)**: Depends on Phase 3 (US2) because linking only applies to manual elections
- **Phase 5 (US4 source filter)**: Depends on Phase 1 (service/router changes); benefits from US1/US2 for test data but service change is independent
- **Phase 6 (E2E)**: Depends on Phases 2–5 all complete
- **Phase 7 (Polish)**: Depends on Phase 6 completion

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 1 — no dependency on US2, US3, US4
- **US2 (P2)**: Can start after Phase 1 — no dependency on US1; can run in parallel with US1
- **US3 (P3)**: Depends on US2 — linking is only meaningful for manually created elections
- **US4 (P4)**: Service/router change is independent after Phase 1; integration tests need elections of each source type (produced by US1/US2/US3)

### Parallel Opportunities

- T003, T004, T005 (schema tasks) can run in parallel within Phase 1
- T007, T008 (US1 test writing) can run in parallel
- T014, T015 (US2 test writing) can run in parallel
- T020, T021 (US3 test writing) can run in parallel
- T029, T030, T031 (E2E tests) can run in parallel
- T033, T034 (lint + coverage) can run in parallel
- T036, T037 commits can be made in parallel (different scopes)

### Within Each Phase

- Tests MUST be written and confirmed failing before implementation begins
- Service changes before router changes (router calls service)
- Lint passes before every commit

---

## Key Risks and Mitigations (from research.md)

| Risk | Task(s) | Mitigation |
|---|---|---|
| `refresh_single_election` crashes on NULL `data_source_url` | T018 | Add null-guard before HTTP request |
| import-feed path forgets `source="sos_feed"` | T017 | Audit all `Election(...)` constructors before commit |
| Refresh loop processes soft-deleted elections | T009 | Add `deleted_at IS NULL` to `refresh_all_active_elections` query |
| Duplicate feed+ballot_item on link | T022 | SELECT check before commit; raise DuplicateElectionError → 409 |
| Existing tests break on `ElectionCreateRequest.source` now required | T006 | Run `uv run pytest --collect-only` after Phase 1 to catch breakage early |
