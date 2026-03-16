# Phase 7: Search and Filters - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Add four new query parameters to `GET /api/v1/elections`: free-text search (`q`), race category filter (`race_category`), county filter (`county`), and exact date filter (`election_date`). All new filters combine with existing filters using AND logic. No new database columns or migrations — uses existing indexed columns (`district_type`, `eligible_county`, `election_date`, `name`, `district`). Backward compatible — existing behavior unchanged when new params are omitted.

</domain>

<decisions>
## Implementation Decisions

### Race category mapping
- `RACE_CATEGORY_MAP` defined as module-level constant in `election_service.py`
- Maps `federal` → `['congressional']`, `state_senate` → `['state_senate']`, `state_house` → `['state_house']`
- `local` implemented as NOT IN (`congressional`, `state_senate`, `state_house`) — future-proof, new district types auto-fall into local
- Phase 8 imports the map from `election_service` for the filter-options endpoint

### Race category validation
- `race_category` query param defined with `Literal['federal', 'state_senate', 'state_house', 'local']` type constraint
- FastAPI auto-returns 422 for invalid values — no custom validation code needed

### Search behavior (q parameter)
- Case-insensitive partial match via ILIKE on `name` OR `district`
- Min 2 chars, max 200 chars (per SRCH-01)
- SQL wildcards `%` and `_` escaped to literal text before building ILIKE (per SRCH-02)
- Escape implemented as a small utility function (unit-testable)

### Filter edge cases
- `election_date` silently overrides `date_from`/`date_to` when both are provided — no 422
- `q` and `district` AND together when both present — consistent with FILT-04 (all filters AND)
- `county` strips leading/trailing whitespace and does case-insensitive exact match via `func.lower()`
- Unknown county values return empty result set (not 422)

### Test strategy
- Integration-heavy: tests hit the API endpoint with various filter params
- Minimal unit tests: RACE_CATEGORY_MAP validation and wildcard escape utility
- Each new filter tested in isolation plus 2-3 combined scenarios (e.g., q+county, race_category+election_date, all-at-once)
- Dedicated test for wildcard escaping (SRCH-02) — searching `100%` and `District_1` to verify literals
- Test fixtures seed elections with `eligible_county` populated — data gap is a production concern, not a code bug
- E2E tests deferred to Phase 8 (per INTG-03)

### Claude's Discretion
- Exact placement of new query params in the route handler signature
- Whether to use a helper function for building the q-search OR condition or inline it
- Integration test file organization (new file vs. existing election test file)
- Exact test fixture data (election names, dates, districts)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### API contract
- `docs/election-search-api-report.md` — Primary contract document defining exact filter behavior, mapping tables, match types, error responses, and deviation notes. Sections 2.1-2.5 define each filter parameter.

### Requirements
- `.planning/REQUIREMENTS.md` — SRCH-01, SRCH-02, FILT-01, FILT-02, FILT-03, FILT-04, INTG-02 are the seven requirements for this phase

### Existing code (modify)
- `src/voter_api/api/v1/elections.py` — Elections router; `list_elections` handler at line 51 gets new query params
- `src/voter_api/services/election_service.py` — `list_elections()` function (line 581) gets new filter conditions + RACE_CATEGORY_MAP constant
- `src/voter_api/schemas/election.py` — May need a RaceCategory type alias for the Literal constraint

### Existing code (reference)
- `src/voter_api/models/election.py` — Election model with `district_type` (line 72), `eligible_county` (line 77), `election_date` (line 43), `name` (line 42), `district` (line 45) columns and their indexes

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `list_elections()` service function: Already builds a dynamic filter chain with `filters: list[ColumnElement[bool]]` — new filters append to the same list
- `Election.district.ilike()`: Existing `district` filter pattern at line 625 of `election_service.py` — same ILIKE pattern used for `q` search
- Column indexes: `idx_elections_district_type`, `idx_elections_eligible_county`, `idx_elections_election_date` already exist — no new indexes needed

### Established Patterns
- Route handlers are thin: declare params, call service, return response — all filter logic lives in the service layer
- All query params use FastAPI `Query()` with descriptions — follow the same pattern for new params
- Pydantic `Literal` types used for enum-like constraints (see `ElectionStatus`, `ElectionType`)

### Integration Points
- `src/voter_api/api/v1/elections.py:list_elections` — Add 4 new `Query()` params, pass through to service
- `src/voter_api/services/election_service.py:list_elections` — Add 4 new filter conditions to the `filters` list
- `tests/integration/test_api/` — Add filter integration tests

</code_context>

<specifics>
## Specific Ideas

No specific requirements — the contract document (`docs/election-search-api-report.md`) defines the behavior comprehensively. Follow it as the source of truth.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-search-and-filters*
*Context gathered: 2026-03-16*
