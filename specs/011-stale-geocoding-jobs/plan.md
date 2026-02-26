# Implementation Plan: Stale Geocoding Job Detection & Cancellation

**Branch**: `011-stale-geocoding-jobs` | **Date**: 2026-02-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-stale-geocoding-jobs/spec.md`

## Summary

Add stale geocoding job recovery on server startup (replicating the existing `_recover_stale_analysis_runs()` pattern), admin cancel/mark-as-failed endpoints, and in-loop cancellation detection in the background geocoding task. No new models or migrations needed — all changes target existing code paths.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x (async), Pydantic v2, Loguru
**Storage**: PostgreSQL 15+ / PostGIS 3.x (existing `geocoding_jobs` table)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux server
**Project Type**: Single project (API + CLI)
**Performance Goals**: Cancel/mark-as-failed endpoints respond within 2 seconds (SC-002)
**Constraints**: No new migrations; use existing `started_at`, `completed_at`, `error_log`, `status` fields
**Scale/Scope**: Feature touches 4 existing files + adds tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Library-First Architecture | PASS | No new library needed — this extends existing service + API layers. The startup recovery is app-level infrastructure (same as the AnalysisRun pattern). |
| II. Code Quality (NON-NEGOTIABLE) | PASS | All new code will have type hints, Google-style docstrings, and pass ruff. |
| III. Testing Discipline (NON-NEGOTIABLE) | PASS | Unit tests for service functions, integration tests for API endpoints, E2E smoke tests for new endpoints. |
| IV. Twelve-Factor Configuration | PASS | No new config; uses existing settings. |
| V. Developer Experience | PASS | No new CLI commands; existing `uv run` workflow unchanged. |
| VI. API Documentation | PASS | New endpoints auto-documented via FastAPI/Pydantic schemas. |
| VII. Security by Design | PASS | Cancel/mark-as-failed restricted to admin role via `require_role("admin")`. Input validated via Pydantic. |
| VIII. CI/CD & Version Control | PASS | Work on feature branch with conventional commits. |

No violations. Complexity Tracking section not needed.

## Project Structure

### Documentation (this feature)

```text
specs/011-stale-geocoding-jobs/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal — no new models)
├── quickstart.md        # Phase 1 output
└── contracts/
    └── openapi-patch.yaml  # Phase 1 output — new endpoint contracts
```

### Source Code (repository root)

```text
src/voter_api/
├── main.py                          # ADD _recover_stale_geocoding_jobs()
├── services/geocoding_service.py    # ADD cancel_geocoding_job(), mark_geocoding_job_failed()
│                                    # MODIFY process_geocoding_job() — add cancellation check
├── api/v1/geocoding.py              # ADD PATCH /jobs/{job_id}/cancel, PATCH /jobs/{job_id}/fail
└── schemas/geocoding.py             # ADD CancelJobResponse, MarkFailedRequest schemas

tests/
├── unit/test_main_recovery.py       # Tests for _recover_stale_geocoding_jobs()
├── integration/test_api/test_geocode_endpoint.py  # ADD cancel/fail endpoint tests
└── e2e/test_smoke.py                # ADD TestGeocoding cancel/fail smoke tests
```

**Structure Decision**: Single project, extending existing service/API/schema layers. No new libraries or architectural changes.

## Design Decisions

### D1: Startup Recovery Pattern

Replicate `_recover_stale_analysis_runs()` exactly. Key differences from AnalysisRun:
- **AnalysisRun.notes** is `Text` (string) — concatenation with `+` and `case()` works.
- **GeocodingJob.error_log** is `JSONB` (array of dicts) — must use `func.coalesce()` + `||` (JSONB concatenation) to append a recovery entry as a JSON array element.

Recovery SQL pattern:
```python
update(GeocodingJob)
    .where(GeocodingJob.status.in_(["running", "pending"]))
    .values(
        status="failed",
        error_log=func.coalesce(GeocodingJob.error_log, func.cast(literal("[]"), JSONB))
            + func.cast(literal('[{"error": "Server restarted while task was in progress"}]'), JSONB),
        completed_at=func.now(),
    )
```

### D2: Cancel & Mark-as-Failed Endpoints

Two PATCH endpoints under the existing `/geocoding` router:
- `PATCH /api/v1/geocoding/jobs/{job_id}/cancel` — admin only
- `PATCH /api/v1/geocoding/jobs/{job_id}/fail` — admin only, accepts optional `reason` body

Both reject requests where the job is already in a terminal state (`completed`, `failed`, `cancelled`) with HTTP 409 Conflict.

### D3: In-Loop Cancellation Detection (FR-012)

Add a status re-read at the top of the batch processing `while` loop in `process_geocoding_job()`. Before each batch:
1. Re-read `GeocodingJob.status` from DB
2. If status is in terminal states, log, update progress, and return early

This is a cooperative cancellation — the background task checks at batch boundaries, not mid-batch.

### D4: Terminal Status Constants

Define `TERMINAL_STATUSES` as a module-level frozenset in `geocoding_service.py`:
```python
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "cancelled"})
```

## File Change Summary

| File | Action | Changes |
|---|---|---|
| `src/voter_api/main.py` | MODIFY | Add `_recover_stale_geocoding_jobs()` function + call in `lifespan()` |
| `src/voter_api/services/geocoding_service.py` | MODIFY | Add `TERMINAL_STATUSES`, `cancel_geocoding_job()`, `mark_geocoding_job_failed()`; modify `process_geocoding_job()` batch loop |
| `src/voter_api/api/v1/geocoding.py` | MODIFY | Add two PATCH endpoints |
| `src/voter_api/schemas/geocoding.py` | MODIFY | Add `CancelJobResponse`, `MarkFailedRequest` schemas |
| `tests/unit/test_main_recovery.py` | CREATE | Unit tests for `_recover_stale_geocoding_jobs()` |
| `tests/integration/test_api/test_geocode_endpoint.py` | MODIFY | Add cancel/fail endpoint integration tests |
| `tests/e2e/test_smoke.py` | MODIFY | Add cancel/fail E2E smoke tests |
