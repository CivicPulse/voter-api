# Tasks: Stale Geocoding Job Detection & Cancellation

**Input**: Design documents from `/specs/011-stale-geocoding-jobs/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi-patch.yaml

**Tests**: Included — constitution mandates testing discipline (Principle III) and plan explicitly lists test files.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Shared constants and cooperative cancellation infrastructure used by all user stories

**⚠️ CRITICAL**: US2 and US3 cannot begin until this phase is complete (US1 is independent and can run in parallel)

- [x] T001Add `TERMINAL_STATUSES` frozenset constant and cooperative cancellation check to `process_geocoding_job()` batch loop in `src/voter_api/services/geocoding_service.py` — define `TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})` at module level; at the top of the `while offset < total:` loop (line ~494), add a fresh DB query `select(GeocodingJob.status).where(GeocodingJob.id == job.id)` and if status is in `TERMINAL_STATUSES`, log a warning, save current progress counts, and `return job` early (FR-012, D3, D4)
- [x] T001b Add unit tests for cooperative cancellation check in `tests/unit/test_geocoding_service_cancel.py` — test cases: (1) job status changed to "cancelled" mid-batch → function stops processing and returns early with progress preserved, (2) job status changed to "failed" mid-batch → same early return, (3) job status remains "running" → processing continues normally; mock the DB session to return the terminal status on the re-read query (FR-012)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 2: User Story 1 — Automatic Stale Job Recovery on Server Restart (Priority: P1) 🎯 MVP

**Goal**: On server restart, all geocoding jobs stuck in "running" or "pending" are automatically marked as "failed" with a recovery note appended to error_log, preventing phantom jobs.

**Independent Test**: Create a geocoding job in "running" status, restart the server, verify the job is now "failed" with error_log containing "Server restarted while task was in progress" and completed_at set.

### Implementation for User Story 1

- [x] T002 [US1] Implement `_recover_stale_geocoding_jobs()` async function in `src/voter_api/main.py` — replicate the `_recover_stale_analysis_runs()` pattern (lines 22–52) but adapted for GeocodingJob: use `update(GeocodingJob).where(GeocodingJob.status.in_(["running", "pending"]))` with JSONB array append for error_log via `func.coalesce(GeocodingJob.error_log, func.cast(literal("[]"), JSONB)) + func.cast(literal('[{"error": "Server restarted while task was in progress"}]'), JSONB)`, set `completed_at=func.now()`, set `status="failed"`, log warning with rowcount (FR-001 through FR-005, R1, R2)
- [x] T003 [US1] Call `_recover_stale_geocoding_jobs()` in the `lifespan()` function in `src/voter_api/main.py` — add a `try/except Exception` block after the existing `_recover_stale_analysis_runs()` call (line ~66), logging a warning on failure for graceful handling when the table doesn't exist yet (FR-006)
- [x] T004 [US1] Add unit tests for stale geocoding job recovery in `tests/unit/test_main_recovery.py` — test cases: (1) running job recovered to failed with recovery note and completed_at, (2) pending job recovered, (3) no stale jobs = no modifications and no warning logged, (4) existing error_log entries preserved with recovery note appended, (5) function handles missing table gracefully

**Checkpoint**: Server startup now automatically recovers stale geocoding jobs. Delivers immediate value — no manual intervention needed.

---

## Phase 3: User Story 2 — Administrator Manually Cancels a Geocoding Job (Priority: P2)

**Goal**: Admin can cancel a running/pending geocoding job via PATCH endpoint, which immediately sets status to "cancelled" with completion timestamp. Background task detects the cancellation at the next batch boundary via the cooperative check from T001.

**Independent Test**: Create a geocoding job, call `PATCH /api/v1/geocoding/jobs/{job_id}/cancel` as admin, verify status changes to "cancelled" with completed_at set.

### Implementation for User Story 2

- [x] T005 [P] [US2] Add `CancelJobResponse` Pydantic schema to `src/voter_api/schemas/geocoding.py` — fields: `id` (uuid.UUID), `status` (str), `completed_at` (datetime), `message` (str); note: `message` has no ORM counterpart, so the endpoint must construct the response manually rather than using `model_validate(job)` (per contracts/openapi-patch.yaml CancelJobResponse)
- [x] T006 [US2] Implement `cancel_geocoding_job()` async service function in `src/voter_api/services/geocoding_service.py` — accepts `session` and `job_id` (uuid.UUID); use an atomic `update(GeocodingJob).where(GeocodingJob.id == job_id, GeocodingJob.status.not_in(TERMINAL_STATUSES)).values(status="cancelled", completed_at=datetime.now(UTC)).returning(GeocodingJob)` pattern to eliminate read-check-update race conditions (spec edge case: concurrent cancellation); if rowcount == 0, re-read the job to distinguish 404 (not found) from 409 (already terminal); commits and returns the updated job (FR-007, FR-009, FR-011, D2)
- [x] T007 [US2] Add `PATCH /jobs/{job_id}/cancel` endpoint to `src/voter_api/api/v1/geocoding.py` — admin-only via `dependencies=[Depends(require_role("admin"))]`; calls `cancel_geocoding_job()`; returns `CancelJobResponse` with message "Job cancelled successfully"; raises HTTPException 404/409 for not-found/terminal-state (FR-010, contracts/openapi-patch.yaml); import `cancel_geocoding_job` from geocoding_service
- [x] T008 [US2] Add integration tests for cancel endpoint in `tests/integration/test_api/test_geocode_endpoint.py` — test cases: (1) cancel running job → 200 with status "cancelled", (2) cancel pending job → 200, (3) cancel completed job → 409, (4) cancel failed job → 409, (5) viewer/analyst gets 403, (6) unauthenticated gets 401, (7) unknown job_id gets 404; mock `cancel_geocoding_job` service function
- [x] T009 [US2] Add E2E smoke tests for cancel endpoint in `tests/e2e/test_smoke.py` — add to `TestGeocoding` class: (1) `test_cancel_job_requires_admin` — viewer client gets 403, (2) `test_cancel_nonexistent_job` — admin client gets 404 for random UUID

**Checkpoint**: Administrators can now cancel stuck or unwanted geocoding jobs via API.

---

## Phase 4: User Story 3 — Administrator Marks a Geocoding Job as Failed (Priority: P3)

**Goal**: Admin can mark a running/pending job as failed with an optional reason via PATCH endpoint. Reason is recorded in error_log. Reuses `CancelJobResponse` schema from US2.

**Independent Test**: Call `PATCH /api/v1/geocoding/jobs/{job_id}/fail` with `{"reason": "Bad data"}` as admin, verify status is "failed", error_log contains the reason, and completed_at is set.

### Implementation for User Story 3

- [x] T010 [P] [US3] Add `MarkFailedRequest` Pydantic schema to `src/voter_api/schemas/geocoding.py` — fields: `reason` (str | None, max_length=1000, default=None) (per contracts/openapi-patch.yaml MarkFailedRequest)
- [x] T011 [US3] Implement `mark_geocoding_job_failed()` async service function in `src/voter_api/services/geocoding_service.py` — accepts `session`, `job_id` (uuid.UUID), `reason` (str | None); use an atomic update pattern matching T006: `update(GeocodingJob).where(GeocodingJob.id == job_id, GeocodingJob.status.not_in(TERMINAL_STATUSES)).values(status="failed", completed_at=datetime.now(UTC), error_log=<append if reason>).returning(GeocodingJob)`; if reason provided, use JSONB concatenation (`func.coalesce(error_log, '[]'::jsonb) || '[{"error": reason}]'::jsonb`) to atomically append to error_log; if rowcount == 0, re-read the job to distinguish 404 from 409; commits and returns updated job (FR-008, FR-009, FR-011, D2)
- [x] T012 [US3] Add `PATCH /jobs/{job_id}/fail` endpoint to `src/voter_api/api/v1/geocoding.py` — admin-only via `dependencies=[Depends(require_role("admin"))]`; accepts optional `MarkFailedRequest` body; calls `mark_geocoding_job_failed()`; returns `CancelJobResponse` with message "Job marked as failed"; raises HTTPException 404/409 (FR-010, contracts/openapi-patch.yaml); import `mark_geocoding_job_failed` from geocoding_service
- [x] T013 [US3] Add integration tests for fail endpoint in `tests/integration/test_api/test_geocode_endpoint.py` — test cases: (1) mark running job as failed with reason → 200, reason in error_log, (2) mark pending job as failed without reason → 200, (3) mark completed job as failed → 409, (4) viewer/analyst gets 403, (5) unauthenticated gets 401
- [x] T014 [US3] Add E2E smoke tests for fail endpoint in `tests/e2e/test_smoke.py` — add to `TestGeocoding` class: (1) `test_fail_job_requires_admin` — viewer client gets 403, (2) `test_fail_nonexistent_job` — admin client gets 404 for random UUID

**Checkpoint**: All three user stories are now independently functional.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all user stories

- [x] T015 [P] Add contract tests for cancel and fail endpoints in `tests/contract/test_geocoding_contract.py` (existing file) — verify response schemas from `PATCH /jobs/{job_id}/cancel` (200, 409) and `PATCH /jobs/{job_id}/fail` (200, 409) match `contracts/openapi-patch.yaml` CancelJobResponse and ErrorResponse shapes (Constitution Principle III: tests in `unit/`, `integration/`, and `contract/` directories)
- [x] T016 Run `uv run ruff check .` and `uv run ruff format --check .` to verify zero lint/format violations across all changed files
- [x] T017 Run full test suite with coverage: `uv run pytest --cov=voter_api --cov-report=term-missing` and verify ≥90% coverage threshold; run `uv run pytest tests/e2e/ --collect-only` to confirm all new E2E tests are discovered

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: No dependency on Phase 1 (recovery function is self-contained in main.py)
- **US2 (Phase 3)**: Depends on Phase 1 (cancel service uses `TERMINAL_STATUSES`; cooperative check needed for full cancel flow)
- **US3 (Phase 4)**: Depends on Phase 1 (`TERMINAL_STATUSES`) and Phase 3 (reuses `CancelJobResponse` schema from T005)
- **Polish (Phase 5)**: Depends on all previous phases

### User Story Dependencies

- **US1 (P1)**: Independent — only touches `main.py` and its own test file
- **US2 (P2)**: Depends on Foundational (T001) for `TERMINAL_STATUSES` and batch loop check
- **US3 (P3)**: Depends on US2 for `CancelJobResponse` schema (T005) and Foundational for `TERMINAL_STATUSES`

### Within Each User Story

- Schema before service (service returns schema-compatible data)
- Service before endpoint (endpoint calls service)
- Implementation before tests (tests validate implementation)

### Parallel Opportunities

**Phase 1 + Phase 2 can run in parallel** since they touch different files:
- T001 modifies `geocoding_service.py`
- T002/T003 modify `main.py`

**Within Phase 3** (US2):
- T005 (schema) can run in parallel with T006 (service) since they're in different files
- T007 (endpoint) depends on both T005 and T006

**Within Phase 4** (US3):
- T010 (schema) can run in parallel with T011 (service)
- T012 (endpoint) depends on both T010 and T011

---

## Parallel Example: Phases 1 + 2

```bash
# These can run in parallel (different files):
Task: T001 — "Add TERMINAL_STATUSES and cooperative cancellation to geocoding_service.py"
Task: T002 — "Implement _recover_stale_geocoding_jobs() in main.py"
Task: T003 — "Call recovery in lifespan() in main.py"
```

## Parallel Example: User Story 2

```bash
# Schema and service in parallel (different files):
Task: T005 — "Add CancelJobResponse schema to schemas/geocoding.py"
Task: T006 — "Implement cancel_geocoding_job() in services/geocoding_service.py"

# Then endpoint (depends on both):
Task: T007 — "Add PATCH cancel endpoint to api/v1/geocoding.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (T001, T001b)
2. Complete Phase 2: US1 — Startup Recovery (T002–T004)
3. **STOP and VALIDATE**: Restart server with stale jobs → verify recovery
4. Deploy if ready — immediate value, zero phantom jobs

### Incremental Delivery

1. Phase 1 (Foundational) + Phase 2 (US1) → Startup recovery works → Deploy
2. Phase 3 (US2) → Admin can cancel jobs → Deploy
3. Phase 4 (US3) → Admin can mark jobs as failed → Deploy
4. Phase 5 (Polish) → Full validation → Final deploy

---

## Notes

- No new models or migrations — all changes extend existing code
- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Error log append uses JSONB concatenation in SQL for both bulk recovery (T002) and atomic mark-as-failed (T011); cancel (T006) does not modify error_log
- Commit after each completed user story phase
- Total: 18 tasks across 5 phases
