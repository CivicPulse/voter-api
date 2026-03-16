# Phase 8: Filter Options and E2E - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Dynamic filter-options endpoint returning valid dropdown values from live election data, plus comprehensive E2E test coverage for all v1.1 endpoints (capabilities, search/filter params, filter-options). No new database columns or migrations — queries existing indexed columns.

</domain>

<decisions>
## Implementation Decisions

### Response shape
- Simple string arrays matching the voter filter-options pattern: `{"race_categories": [...], "counties": [...], "election_dates": [...]}`
- Only return category/county/date values that have at least one non-deleted election (no empty options in dropdowns)
- Election dates sorted descending (newest first)
- Include a top-level `total_elections` integer field alongside the filter arrays
- Counties title-case normalized regardless of DB storage casing

### Auth & caching
- Public endpoint (no auth required) — consistent with /capabilities and elections list
- Cache-Control: public, max-age=300 (5-minute cache for dynamic data)

### E2E seed data
- Add 4-5 elections covering all race categories: federal (congressional), state_senate, state_house, local (null/other district_type), plus one soft-deleted election
- Soft-deleted election seeded in seed_database (deleted_at set) for exclusion tests
- Also test inline create-then-delete to verify dynamic soft-delete exclusion
- Shared seed data — new elections visible to all tests; update existing count assertions (>= instead of ==)
- Each seeded election should have district_type and eligible_county populated to exercise Phase 7 filters

### Endpoint behavior
- Empty database or all-deleted returns empty arrays: `{"race_categories": [], "counties": [], "election_dates": [], "total_elections": 0}`
- No 404 or special status for empty results — 200 with empty arrays

### Claude's Discretion
- Exact seeded election names, dates, and district values
- Internal query implementation (single query vs multiple)
- Title-case normalization approach (Python str.title() or SQL)
- E2E test organization within TestElections or new test class
- Route registration order (must be before /{election_id} catch-all — already established pattern from Phase 6)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Filter options endpoint
- `.planning/REQUIREMENTS.md` — DISC-02 requirement (filter-options endpoint returns valid values for dropdowns)
- `.planning/ROADMAP.md` — Phase 8 success criteria (SC1-SC4)

### Existing patterns
- `src/voter_api/services/voter_service.py` lines 192-260 — `get_voter_filter_options()` is the existing filter-options pattern (DISTINCT queries, sorted arrays, dict response)
- `src/voter_api/services/election_service.py` lines 56-61 — `RACE_CATEGORY_MAP` and `_NON_LOCAL_TYPES` constants used for race_category mapping
- `src/voter_api/api/v1/elections.py` lines 122-129 — `/capabilities` endpoint (route ordering reference, caching pattern)

### E2E test infrastructure
- `tests/e2e/conftest.py` — Seed data fixtures, fixed UUIDs, authenticated client helpers
- `tests/e2e/test_smoke.py` — Existing test classes and assertion patterns
- `CLAUDE.md` §E2E Tests — Rules for updating E2E tests when API changes

### Prior phase context
- `.planning/STATE.md` — Accumulated decisions section (race_category mapping, county filter, q param constraints)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `voter_service.get_voter_filter_options()`: Pattern for DISTINCT queries returning sorted string arrays — election version follows same shape
- `RACE_CATEGORY_MAP` in election_service: Already maps category keys to district_type values; can be inverted for filter-options
- `CapabilitiesResponse` schema: Already references `filter_options: True`; filter-options endpoint fulfills this contract
- `_make_client()` helper in conftest: Shared client factory for role-specific E2E clients

### Established Patterns
- Route ordering: Static routes (/capabilities) registered before /{election_id} catch-all — filter-options must follow same pattern
- Soft-delete filtering: `Election.deleted_at.is_(None)` used throughout election_service queries
- E2E seed data: `pg_insert().on_conflict_do_update()` for idempotent seeding with fixed UUIDs
- Cache-Control headers: Set directly on Response object in route handlers

### Integration Points
- Elections router (`api/v1/elections.py`): New `/filter-options` route registered after `/capabilities` but before `/{election_id}`
- Election service: New `get_filter_options()` function querying DISTINCT values
- Election schemas: New `FilterOptionsResponse` Pydantic model
- E2E conftest: New election seed rows with district_type and eligible_county populated

</code_context>

<specifics>
## Specific Ideas

- Both seeded soft-deleted election AND inline create-then-delete test for belt-and-suspenders coverage
- Title-case normalize counties (e.g., "BIBB" -> "Bibb") for consistent frontend display
- total_elections count lets frontend display "Showing filters for N elections" without a separate API call

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-filter-options-and-e2e*
*Context gathered: 2026-03-16*
