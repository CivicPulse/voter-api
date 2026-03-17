---
phase: 10-fix-mismatch-filter-sql-defect
plan: 01
subsystem: api
tags: [sqlalchemy, postgresql, jsonb, alembic, testing]

# Dependency graph
requires:
  - phase: 09-context-aware-mismatch-filter
    provides: _build_mismatch_filter, _latest_analysis_subquery, list_election_participants with DISTINCT ON deduplication subquery

provides:
  - Fixed _build_mismatch_filter using latest_ar.c.mismatch_details (subquery alias) instead of ORM table column
  - Compile-and-assert unit tests verifying compiled SQL FROM clause correctness
  - E2E deduplication test with two analysis runs per voter (old mismatch, new match)
  - GIN index migration on analysis_results.mismatch_details for JSONB containment queries

affects:
  - voter-history participation filtering correctness
  - any future work on analysis_results or mismatch filter logic

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Subquery alias passthrough: pass latest_ar through call chain (_latest_analysis_subquery → list_election_participants → _apply_voter_filters → _build_mismatch_filter) to avoid implicit cross join"
    - "Compile-and-assert SQL testing: compile full joined query with PostgreSQL dialect, assert FROM clause structure not just isinstance(ClauseElement)"

key-files:
  created:
    - alembic/versions/030_add_gin_index_analysis_results_mismatch_details.py
  modified:
    - src/voter_api/services/voter_history_service.py
    - tests/unit/test_services/test_voter_history_service.py
    - tests/e2e/conftest.py
    - tests/e2e/test_smoke.py

key-decisions:
  - "latest_ar passed as first param to _build_mismatch_filter — single subquery instance, same alias used in JOIN and WHERE"
  - "_apply_voter_filters accepts latest_ar: Any = None; guard requires latest_ar is not None to activate mismatch filter"
  - "_compile_query uses postgresql.dialect() without literal_binds (JSONB list values cannot be rendered as literals)"
  - "GIN index is full (not partial) — covers all @> containment queries on mismatch_details"

patterns-established:
  - "Compile-and-assert: use str(query.compile(dialect=postgresql.dialect())) to inspect FROM/WHERE structure without running DB"
  - "Subquery column reference: use subquery_alias.c.column_name, never ORM model columns, in functions that receive a subquery alias"

requirements-completed: [MISMATCH-01]

# Metrics
duration: 25min
completed: 2026-03-16
---

# Phase 10 Plan 01: Fix Mismatch Filter SQL Defect Summary

**Fixed implicit cross join in _build_mismatch_filter by replacing ORM column references with latest_ar.c.mismatch_details, verified by compile-and-assert unit tests and an E2E deduplication smoke test**

## Performance

- **Duration:** 25 min
- **Started:** 2026-03-16T23:20:00Z
- **Completed:** 2026-03-16T23:45:00Z
- **Tasks:** 3
- **Files modified:** 5 (+ 1 created)

## Accomplishments

- Eliminated structural SQL defect: `_build_mismatch_filter` now uses `latest_ar.c.mismatch_details` (subquery alias column) instead of `AnalysisResult.mismatch_details` (ORM table column), preventing the implicit Cartesian product that bypassed DISTINCT ON deduplication
- Replaced 4 weak `isinstance(ClauseElement)` tests with 5 compile-and-assert tests that compile the full joined query to PostgreSQL SQL and assert `latest_ar` is referenced and `analysis_results` does not appear after the WHERE clause
- Added E2E deduplication test with two seeded analysis results (old: mismatch, new: match) that verifies the DISTINCT ON subquery correctly uses only the latest result
- Created Alembic migration `030_gin_mismatch_details` adding a GIN index on `analysis_results.mismatch_details` for JSONB containment query performance

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix _build_mismatch_filter ORM column reference** - `f398a96` (fix)
2. **Task 2: Compile-and-assert SQL correctness tests** - `3da454a` (test) + `df876cb` (style: ruff format)
3. **Task 3: E2E deduplication test, seed data, GIN index migration** - `c1200b3` (feat)

## Files Created/Modified

- `src/voter_api/services/voter_history_service.py` - Added `latest_ar` param to `_build_mismatch_filter` and `_apply_voter_filters`; replaced ORM column refs with subquery alias refs; pass `latest_ar` from call site
- `tests/unit/test_services/test_voter_history_service.py` - Replaced `TestBuildMismatchFilter` with 5 compile-and-assert tests; added `_compile_query` helper; imported `_latest_analysis_subquery`, `Voter`, `select`, `postgresql`
- `tests/e2e/conftest.py` - Added 6 UUID constants; seeded `ELECTION_STATE_SENATE_FULTON_ID`, `VOTER_HISTORY_ID_SENATE`, two `AnalysisRun` rows, two `AnalysisResult` rows; added teardown cleanup
- `tests/e2e/test_smoke.py` - Imported `ELECTION_STATE_SENATE_FULTON_ID`; added `test_participation_mismatch_deduplication_latest_result_used`
- `alembic/versions/030_add_gin_index_analysis_results_mismatch_details.py` - GIN index on `analysis_results.mismatch_details`, `down_revision = "f4b2c6d9e013"`

## Decisions Made

- Used `postgresql.dialect()` without `literal_binds=True` in `_compile_query` — JSONB list values cannot be rendered as literals by SQLAlchemy's PostgreSQL compiler
- Guard in `_apply_voter_filters` now requires `latest_ar is not None` (in addition to `district_type`) to ensure mismatch filter is never applied without the subquery alias
- `latest_ar if mismatch_filter_active else None` is safe at the call site — Python ternary only evaluates the true branch (where `latest_ar` is defined) when `mismatch_filter_active=True`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `literal_binds=True` incompatible with JSONB list parameters**
- **Found during:** Task 2 (compile-and-assert tests)
- **Issue:** `_compile_query` with `literal_binds=True` raised `CompileError: No literal value renderer is available for literal value "[{'boundary_type': 'state_senate'}]" with datatype JSONB`
- **Fix:** Removed `compile_kwargs={"literal_binds": True}` from `_compile_query` — structural FROM/WHERE inspection does not require literal values
- **Files modified:** `tests/unit/test_services/test_voter_history_service.py`
- **Verification:** All 5 compile-and-assert tests pass
- **Committed in:** `3da454a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test helper)
**Impact on plan:** Minor adjustment to `_compile_query` helper — tests still achieve the same structural assertion goal. No scope changes.

## Issues Encountered

None beyond the JSONB literal rendering issue documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MISMATCH-01 requirement is now fully satisfied: the structural SQL defect is fixed, tests verify correctness at the SQL level, and E2E deduplication test provides runtime verification
- GIN index migration `030_gin_mismatch_details` is ready to apply on next `alembic upgrade head`
- No blockers for milestone v1.2 closure

---
*Phase: 10-fix-mismatch-filter-sql-defect*
*Completed: 2026-03-16*
