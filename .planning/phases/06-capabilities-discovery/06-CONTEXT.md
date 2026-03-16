# Phase 6: Capabilities Discovery - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Static capabilities endpoint (`GET /api/v1/elections/capabilities`) that lets API consumers discover which search and filter parameters the elections API supports. Must be registered before the `/{election_id}` catch-all route to avoid path conflicts. All existing election endpoints must continue to work identically.

</domain>

<decisions>
## Implementation Decisions

### Response shape
- Minimal response: flat list of filter names, endpoint flags (no version field — contract document omits it)
- Ship the full filter list from day one (all 5 filters + filter_options: true)
- Phases 7-8 implement the actual filter logic behind these names
- No formal additive-only guarantee — the response may change; frontend should re-fetch on session start

### Response schema
- Define a `CapabilitiesResponse` Pydantic model in `schemas/election.py`
- Ensures response appears in OpenAPI docs with a named schema
- Follows existing codebase convention: every endpoint has a `response_model`

### Auth and caching
- Public endpoint — no authentication required (frontend needs this before user login)
- Cache-Control: public, max-age=3600 (1 hour short cache)

### Test coverage
- Phase 6 includes unit + integration tests:
  - Unit test for the static response shape (validates Pydantic model)
  - Integration test verifying `/capabilities` returns 200 with expected JSON
  - Integration test proving `/capabilities` isn't swallowed by `/{election_id}` route
  - Parameterized regression test hitting all existing election endpoints to confirm nothing broke
- E2E smoke tests deferred to Phase 8

### Claude's Discretion
- Exact placement of the capabilities route within `elections.py` (before `/{election_id}` is the only requirement)
- Whether to define the supported filters list as a module-level constant or inline
- Test file organization (new file vs. added to existing election test file)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Capabilities contract
- `docs/election-search-api-report.md` — Frontend integration report defining the exact capabilities response shape (Section 1), filter parameter semantics (Section 2), and deviation notes. This is the primary contract document.

### Requirements
- `.planning/REQUIREMENTS.md` — DISC-01 (capabilities endpoint) and INTG-01 (route ordering) are the two requirements for this phase

### Existing code
- `src/voter_api/api/v1/elections.py` — Current elections router; `/{election_id}` at line 171 is the route that will conflict with `/capabilities`
- `src/voter_api/api/router.py` — Router registration; elections_router included at line 50
- `src/voter_api/schemas/election.py` — Where `CapabilitiesResponse` should be added
- `src/voter_api/models/election.py` — Election model with `district_type`, `eligible_county`, `election_date` fields that the capabilities response advertises

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `elections_router` (APIRouter): New `/capabilities` route added to this existing router
- `PaginationMeta`, `ErrorResponse` in `schemas/common.py`: Established response patterns to follow
- Existing election endpoint patterns: Thin handler → service call, `response_model=` on every route

### Established Patterns
- Route handlers are thin wrappers: declare route, call service, return response
- All response shapes use Pydantic models with `response_model=` on the decorator
- Cache-Control headers set directly on `Response` object (see `get_election_results` pattern)
- Static routes registered before parameterized routes within a router file

### Integration Points
- `src/voter_api/api/v1/elections.py` — Add `/capabilities` route before `/{election_id}` declaration
- `src/voter_api/schemas/election.py` — Add `CapabilitiesResponse` model
- `tests/integration/test_api/` — Add capabilities tests alongside existing election API tests

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. The `election-search-api-report.md` defines the contract clearly.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-capabilities-discovery*
*Context gathered: 2026-03-16*
