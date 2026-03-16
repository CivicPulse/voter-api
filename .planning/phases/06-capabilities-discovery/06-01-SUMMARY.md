---
phase: 06-capabilities-discovery
plan: 01
subsystem: api
tags: [fastapi, pydantic, elections, capabilities, discovery]

# Dependency graph
requires: []
provides:
  - "GET /api/v1/elections/capabilities endpoint returning supported_filters and endpoints"
  - "CapabilitiesResponse Pydantic schema"
  - "Route ordering pattern: static routes before parameterized /{id} routes"
affects: [07-filter-options, 08-election-search]

# Tech tracking
tech-stack:
  added: []
  patterns: ["static discovery endpoint with Cache-Control", "route ordering: static before parameterized"]

key-files:
  created:
    - tests/unit/test_schemas/test_capabilities_schema.py
    - tests/integration/test_api/test_capabilities_api.py
  modified:
    - src/voter_api/schemas/election.py
    - src/voter_api/api/v1/elections.py

key-decisions:
  - "No database dependency for capabilities endpoint — static response with 1-hour cache"
  - "Route placed after list_elections but before admin create, well ahead of /{election_id}"

patterns-established:
  - "Static discovery endpoints: no session dependency, Cache-Control public header, declared before parameterized routes"

requirements-completed: [DISC-01, INTG-01]

# Metrics
duration: 4min
completed: 2026-03-16
---

# Phase 6 Plan 01: Capabilities Discovery Summary

**Static capabilities endpoint returning supported_filters and endpoints with Cache-Control caching and route-ordering guard**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-16T18:19:41Z
- **Completed:** 2026-03-16T18:23:57Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- CapabilitiesResponse Pydantic model with supported_filters (list[str]) and endpoints (dict[str, bool])
- GET /api/v1/elections/capabilities returns contract-compliant JSON with Cache-Control: public, max-age=3600
- Route ordering verified: /capabilities declared before /{election_id} to prevent shadowing
- 9 tests (3 unit + 6 integration) covering shape, contract, caching, shadowing, and regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Add CapabilitiesResponse schema and /capabilities route** - `0edf183` (feat)
2. **Task 2: Add unit and integration tests for capabilities endpoint** - `3fa68b1` (test)

## Files Created/Modified
- `src/voter_api/schemas/election.py` - Added CapabilitiesResponse model after PaginatedElectionListResponse
- `src/voter_api/api/v1/elections.py` - Added /capabilities route handler with CapabilitiesResponse import
- `tests/unit/test_schemas/test_capabilities_schema.py` - Unit tests for schema shape and serialization
- `tests/integration/test_api/test_capabilities_api.py` - Integration tests for endpoint behavior and regression

## Decisions Made
- No database dependency for capabilities endpoint — static response avoids unnecessary DB calls
- Route placed between list_elections and admin create section, well before /{election_id} parameterized route

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Capabilities endpoint establishes route ordering pattern for Phase 7 (filter-options)
- The `endpoints.filter_options: true` field will be truthful once Phase 7 implements the filter-options endpoint
- Pre-existing test failures in unrelated modules (test_attachments_api, test_seed_cmd) are not caused by this plan

---
*Phase: 06-capabilities-discovery*
*Completed: 2026-03-16*
