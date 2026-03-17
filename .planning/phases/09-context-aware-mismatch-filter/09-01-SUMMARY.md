---
phase: 09-context-aware-mismatch-filter
plan: 01
subsystem: api
tags: [fastapi, sqlalchemy, postgresql, jsonb, voter-history, analysis-results]

# Dependency graph
requires:
  - phase: 08-auto-data-import
    provides: analysis_results table with JSONB mismatch_details column
  - phase: 07-analysis
    provides: AnalysisResult model and BOUNDARY_TYPE_TO_VOTER_FIELD mapping
provides:
  - Context-aware mismatch filter on participation endpoint (JSONB lookup scoped to election district_type)
  - MismatchFilterError exception with 422 route handler catch
  - mismatch_district_type metadata field on PaginatedElectionParticipationResponse
  - mismatch_count field on ParticipationStatsResponse
affects: voter-history, analysis, elections

# Tech tracking
tech-stack:
  added: []
  patterns:
    - JSONB containment query via SQLAlchemy AnalysisResult.mismatch_details.contains(type_coerce(..., JSONB_TYPE))
    - DISTINCT ON subquery for latest analysis result per voter (_latest_analysis_subquery)
    - MismatchFilterError(ValueError) for semantic validation raising 422

key-files:
  created: []
  modified:
    - src/voter_api/schemas/voter_history.py
    - src/voter_api/services/voter_history_service.py
    - src/voter_api/api/v1/voter_history.py
    - tests/unit/test_services/test_voter_history_service.py
    - tests/integration/test_voter_history_api.py

key-decisions:
  - "Return 4-tuple from list_election_participants (added district_type_used as 4th element) so route handler can set mismatch_district_type metadata"
  - "Use DISTINCT ON (voter_id) ORDER BY analyzed_at DESC subquery to deduplicate analysis results — avoids double-counting voters with multiple analysis runs"
  - "mismatch_filter_active validated before query building — raises MismatchFilterError immediately for null/unknown district_type elections"
  - "MismatchFilterError caught before ValueError in route handler to ensure 422 not 404 for validation failures"

patterns-established:
  - "JSONB containment filter: AnalysisResult.mismatch_details.contains(type_coerce([{boundary_type: X}], JSONB_TYPE))"
  - "Latest-per-voter subquery: select(AnalysisResult).distinct(voter_id).order_by(voter_id, analyzed_at.desc())"
  - "Semantic validation errors use custom ValueError subclass caught as 422 before generic ValueError/404"

requirements-completed: [MISMATCH-01]

# Metrics
duration: 6min
completed: 2026-03-16
---

# Phase 9 Plan 1: Context-Aware Mismatch Filter Summary

**JSONB containment query on analysis_results.mismatch_details scoped to election district_type replaces blanket Voter.has_district_mismatch boolean filter**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-03-16T21:56:26Z
- **Completed:** 2026-03-16T22:02:03Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Replaced `Voter.has_district_mismatch == value` with a JSONB containment check on `analysis_results.mismatch_details` scoped to the election's `district_type`
- Added `MismatchFilterError` raised for elections with null or unknown district_type, caught as 422 in the route handler
- Added `mismatch_count` to participation stats response (context-aware count of mismatched voters for the election's district type)
- Added `mismatch_district_type` metadata field to participation list response when filter is active

## Task Commits

Each task was committed atomically:

1. **Task 1: Add schemas and MismatchFilterError exception** - `204cd0b` (feat)
2. **Task 2+3: Service layer JSONB filter + route handler wiring** - `cfc7c0e` (feat)

## Files Created/Modified
- `src/voter_api/schemas/voter_history.py` - Added `mismatch_district_type` to PaginatedElectionParticipationResponse, `mismatch_count` to ParticipationStatsResponse
- `src/voter_api/services/voter_history_service.py` - Added `MismatchFilterError`, `_latest_analysis_subquery()`, `_build_mismatch_filter()`, updated `list_election_participants` and `get_participation_stats`
- `src/voter_api/api/v1/voter_history.py` - Updated unpacking to 4-tuple, added `MismatchFilterError` catch as 422, set `mismatch_district_type` on response
- `tests/unit/test_services/test_voter_history_service.py` - Updated 3-tuple unpacking to 4-tuple, updated `test_has_district_mismatch_triggers_join_path` to use valid district_type
- `tests/integration/test_voter_history_api.py` - Updated mock return values from 3-tuple to 4-tuple

## Decisions Made
- Return 4-tuple from `list_election_participants` — cleaner than a dataclass for this small addition; avoids breaking the existing boolean flag pattern
- DISTINCT ON subquery approach for latest analysis per voter — avoids a window function subquery and is idiomatic for PostgreSQL
- Validate district_type before building queries — fail fast on invalid input rather than silently ignoring the filter

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing unit and integration tests to unpack 4-tuple return**
- **Found during:** Task 2 (service layer implementation)
- **Issue:** Changing `list_election_participants` return type from 3-tuple to 4-tuple caused `ValueError: too many values to unpack` in existing tests and route handler, which was being caught as 404
- **Fix:** Updated all 3-tuple unpacking sites in unit tests (6 locations) and integration tests (8 mock return values) plus the route handler
- **Files modified:** tests/unit/test_services/test_voter_history_service.py, tests/integration/test_voter_history_api.py, src/voter_api/api/v1/voter_history.py
- **Verification:** 73 tests pass
- **Committed in:** cfc7c0e (Task 2+3 combined commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug caused by return type change)
**Impact on plan:** Necessary side-effect of the return type change. Task 3 (route handler) was executed alongside Task 2 because the 3-tuple unpacking in the route handler was silently turning the new 4-tuple into a 404. No scope creep.

## Issues Encountered
- Ruff lint: `class MismatchFilterError` placement before constants caused unsorted import block error — fixed with `ruff --fix`
- Ruff lint: Unnecessary `else` after `return` in `_build_mismatch_filter` — fixed with `ruff --fix`

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Context-aware mismatch filter is complete and tested
- No new migrations required — uses existing `analysis_results` table
- Phase 9 is a single-plan phase; milestone v1.2 is complete

---
*Phase: 09-context-aware-mismatch-filter*
*Completed: 2026-03-16*
