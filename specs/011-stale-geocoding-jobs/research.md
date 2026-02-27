# Research: Stale Geocoding Job Detection & Cancellation

**Feature**: 011-stale-geocoding-jobs
**Date**: 2026-02-25

## Research Tasks & Findings

### R1: JSONB Array Append in SQLAlchemy Bulk Update

**Question**: How to append an entry to a JSONB array column (`error_log`) in a bulk `UPDATE` statement without overwriting existing entries?

**Decision**: Use PostgreSQL JSONB concatenation operator `||` via SQLAlchemy's `func.coalesce()` + type cast.

**Rationale**: The `error_log` column is `JSONB` typed as `list[dict] | None`. PostgreSQL's `||` operator concatenates two JSONB arrays. We must coalesce `NULL` to `'[]'::jsonb` first, then concatenate the recovery note as a single-element array.

**Implementation**:
```python
from sqlalchemy import func, literal
from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE
from sqlalchemy.type_coerce import type_coerce

recovery_note = [{"error": "Server restarted while task was in progress"}]

update(GeocodingJob)
    .where(GeocodingJob.status.in_(["running", "pending"]))
    .values(
        status="failed",
        error_log=func.coalesce(GeocodingJob.error_log, type_coerce([], JSONB_TYPE)) +
                  type_coerce(recovery_note, JSONB_TYPE),
        completed_at=func.now(),
    )
```

**Alternatives considered**:
- `func.jsonb_insert()` — only inserts at a path, not appending to root array.
- Python-side read-modify-write — requires loading all rows first, defeats the purpose of a bulk update.
- Storing as `Text` instead of `JSONB` — would require schema change (rejected per spec: no migrations).

---

### R2: Existing Startup Recovery Pattern

**Question**: What exactly does `_recover_stale_analysis_runs()` do, and how should the geocoding version differ?

**Decision**: Follow the same structure with two differences: (1) JSONB array append instead of string concatenation for the notes/error_log field, (2) wrap in `try/except` in `lifespan()` to handle missing table gracefully (FR-006).

**Rationale**: The AnalysisRun recovery uses `case()` + string concatenation because `notes` is a `Text` column. GeocodingJob's `error_log` is `JSONB`, so we use JSONB concat. The try/except wrapper in `lifespan()` already handles the table-not-exists case (same pattern).

**Key observations from existing code**:
- `main.py:22-53` — `_recover_stale_analysis_runs()` is a standalone async function
- `main.py:63-66` — called in `lifespan()` with `try/except Exception` and a warning log
- Uses `get_session_factory()` directly (not dependency injection)
- Uses `result.rowcount` to log the count of recovered runs

---

### R3: Background Task Cancellation Detection

**Question**: How should `process_geocoding_job()` detect that an admin cancelled the job via the API?

**Decision**: Add a status re-read query at the top of the `while offset < total:` loop. If the status is in `TERMINAL_STATUSES`, save progress and return early.

**Rationale**: The background task runs in the same process (`InProcessTaskRunner` uses `asyncio.create_task()`). The cancel endpoint updates the DB directly. The background task needs to re-read the DB status to detect the change. Checking at batch boundaries (every `batch_size` records) is a good granularity — it balances responsiveness with DB query overhead.

**Implementation location**: `geocoding_service.py:494` (start of `while` loop)

**Alternatives considered**:
- Shared in-memory flag — fragile, doesn't survive across module boundaries cleanly.
- `asyncio.Event` — requires passing the event from the API layer to the background task, adds coupling.
- DB polling on a timer — over-engineered; batch boundary check is simpler and sufficient.

---

### R4: HTTP Method for Cancel/Fail Endpoints

**Question**: Should cancel/fail be POST or PATCH?

**Decision**: PATCH — these are partial updates to an existing resource's status field.

**Rationale**: REST convention: PATCH modifies a subset of a resource's fields. POST implies creating a new resource. Since we're updating `status`, `completed_at`, and optionally `error_log` on an existing `GeocodingJob`, PATCH is the correct verb. This aligns with the spec's `PATCH /api/v1/geocoding/jobs/{job_id}/cancel`.

**Alternatives considered**:
- POST — valid for "actions" but PATCH better communicates partial update semantics.
- PUT — would imply replacing the entire resource, which is not the intent.

---

### R5: Error Response for Terminal State Jobs

**Question**: What HTTP status code should be returned when trying to cancel/fail a job that's already in a terminal state?

**Decision**: HTTP 409 Conflict.

**Rationale**: 409 Conflict is appropriate when the request cannot be completed because it conflicts with the current state of the resource. A job in `completed`/`failed`/`cancelled` status cannot be transitioned again. 400 Bad Request could also work but is less specific about the nature of the error.

**Alternatives considered**:
- 400 Bad Request — too generic, doesn't convey the state conflict.
- 422 Unprocessable Entity — more about request validation than state conflicts.
