# Pitfalls Research

**Domain:** Adding search/filter/discovery capabilities to an existing election REST API (FastAPI + SQLAlchemy async + PostgreSQL)
**Researched:** 2026-03-16
**Confidence:** HIGH (based on direct codebase analysis of existing router, service, and model code)

## Critical Pitfalls

### Pitfall 1: FastAPI Route Ordering -- `/{election_id}` Swallows Static Paths

**What goes wrong:**
`GET /elections/capabilities` and `GET /elections/filter-options` are matched by the existing `GET /elections/{election_id}` route (line 171 of `elections.py`). FastAPI evaluates routes in registration order. If the new static endpoints are registered after `/{election_id}`, the UUID path converter rejects "capabilities" as an invalid UUID and returns a 422 validation error instead of routing to the intended handler.

**Why it happens:**
The current `elections.py` registers `/{election_id}` at line 171, before where new endpoints would naturally be appended. Developers adding features often put new routes at the bottom of the file.

**How to avoid:**
Register `/capabilities` and `/filter-options` routes **before** `/{election_id}` in the file. They should go between the `POST "/import-feed"` block (line 146) and `GET "/{election_id}"` (line 171). The existing `POST "/import-feed/preview"` (line 125) already demonstrates this pattern -- it is registered before `/{election_id}` precisely because it is a static sub-path.

**Warning signs:**
- `GET /elections/capabilities` returns 422 with "value is not a valid uuid"
- Tests pass in isolation but fail when the full router is mounted
- The error message mentions `election_id` even though the request targets a static path

**Phase to address:**
Phase 1 (Capabilities endpoint) -- must establish correct route ordering before any other endpoint is added.

---

### Pitfall 2: Race Category Mapping Drift from `district_type` Values

**What goes wrong:**
The `race_category` filter maps frontend display categories (e.g., "Federal", "State", "County", "Municipal") to the existing `district_type` column values. If the mapping is hardcoded and the set of `district_type` values in the database drifts (new import adds "school_board" or "judicial_circuit" not in the mapping), elections silently disappear from filtered results. Users filtering by "County" see incomplete results with no error.

**Why it happens:**
`district_type` is a free-form `String(50)` column (not a DB enum), populated by `election_resolution_service.py` during import. There is no constraint on allowed values. The mapping between frontend categories and database values is a business rule that depends on data imported from external sources (SOS feeds, JSONL pipelines).

**How to avoid:**
1. Define the `race_category -> [district_type values]` mapping as a **single constant dict** in the service layer -- not duplicated in router, service, and frontend.
2. The `/filter-options` endpoint should return `race_category` options derived from this mapping intersected with actual DB values, not from raw `SELECT DISTINCT district_type`.
3. Add a startup or health-check query: `SELECT DISTINCT district_type FROM elections WHERE district_type NOT IN (known_values) AND deleted_at IS NULL` -- log a warning if unmapped values exist.
4. Include the mapping in the `/capabilities` response so the frontend knows exactly what each category includes.

**Warning signs:**
- `/filter-options` returns race categories that produce zero results when applied as a filter
- Elections visible in the unfiltered list disappear when any race category is selected
- New JSONL imports log `district_type` values not present in the mapping

**Phase to address:**
Phase 3 (Race category filter). The mapping constant must be defined before filter-options (Phase 5) to ensure consistency.

---

### Pitfall 3: `eligible_county` NULL Silently Drops Elections from County Filter

**What goes wrong:**
SOS feed elections often have `eligible_county = NULL` because the county is not provided in the feed data. A county filter using `Election.eligible_county == county_name` returns only elections where the column is populated, silently hiding statewide or untagged elections. This is the single most confusing UX issue in the planned feature set.

**Why it happens:**
The `eligible_county` field is populated from candidate CSV imports (COUNTY column) and JSONL pipeline imports, but not from all SOS feed elections or manual election creation. The PROJECT.md already flags this: "eligible_county not populated for all elections" and "Statewide elections should ideally appear in county filter but that requires geospatial logic (deferred)."

**How to avoid:**
1. Accept the limitation explicitly -- county filter only matches elections with a populated `eligible_county`. This is the correct v1.1 behavior.
2. The `/capabilities` response must document coverage: include a `county_filter_note` or similar field indicating partial coverage so the frontend can display an appropriate disclaimer.
3. Do NOT attempt to include statewide elections in county results in this milestone -- that requires boundary joins and geospatial containment checks, correctly deferred per PROJECT.md.
4. The `/filter-options` county list should only return values actually present in the data. If only 3 counties have elections, show 3 options, not all 159 Georgia counties.

**Warning signs:**
- User filters by "Bibb" county and misses a statewide Governor race they expected to see
- `/filter-options` county list is shorter than expected
- QA reports "some elections disappear when I select a county"

**Phase to address:**
Phase 4 (County filter). Document the limitation in capabilities (Phase 1). Statewide inclusion is a backlog item already identified in PROJECT.md.

---

### Pitfall 4: Filter Combination Semantics -- `q` vs `district` Overlap

**What goes wrong:**
The existing `district` query parameter uses ILIKE partial match (line 625 of `election_service.py`). The new `q` text search also searches the `district` column. If both are provided simultaneously, the behavior is confusing: `district=Bibb&q=senate` means "district contains 'Bibb' AND (name contains 'senate' OR district contains 'senate')". The `district` column is effectively filtered twice with different semantics (exact substring AND broad search).

**Why it happens:**
The new `q` parameter overlaps with the existing `district` parameter in scope. The PROJECT.md correctly identifies keeping `district` as partial match to avoid a breaking change, but does not address the interaction when both are provided.

**How to avoid:**
1. All filters are AND-combined (matching the existing pattern). `q` is a single filter clause that ORs across `name` and `district`. The existing `district`, `status`, `election_type`, etc. are separate AND clauses. This is logically consistent.
2. Document the filter combination semantics in the `/capabilities` response: "All filters are combined with AND. The `q` parameter searches across `name` and `district` with OR logic."
3. Verify the frontend will not send both `q` and `district` simultaneously. If it does, the AND combination works but may produce unexpected narrow results.

**Warning signs:**
- Frontend sends both `q` and `district`, gets empty results, files a bug
- API docs do not specify AND vs OR semantics

**Phase to address:**
Phase 2 (Text search). Define and document filter combination semantics before implementation.

---

### Pitfall 5: Wildcard Characters in ILIKE Search Input

**What goes wrong:**
User searches for `q=100%` or `q=John_Doe`. The `%` and `_` characters are SQL wildcards in ILIKE patterns. SQLAlchemy's `ilike()` parameterizes the value (safe from injection), but the wildcard characters still function as wildcards within the LIKE pattern. `%100%%` matches any string containing "100" followed by anything, and `%John_Doe%` matches "John" + any single character + "Doe".

**Why it happens:**
The existing `district` filter on line 625 already has this issue: `Election.district.ilike(f"%{district}%")`. It has been harmless because district values don't contain wildcards. But a general-purpose `q` text search is more likely to receive user input with these characters.

**How to avoid:**
Escape wildcard characters before wrapping in `%...%`:
```python
def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```
Apply to both `q` and `district` filter values. This is a one-line fix but must be done from the start.

**Warning signs:**
- Search for "100%" returns unexpected results
- Difficult to reproduce because most real queries don't contain wildcards

**Phase to address:**
Phase 2 (Text search). Apply the escape helper to all ILIKE filter values, including the existing `district` filter.

---

### Pitfall 6: `selectinload(Election.result)` on Search Queries Loads Unnecessary JSONB

**What goes wrong:**
The existing `list_elections` service function (line 616) eagerly loads the `result` relationship via `selectinload(Election.result)`. The `ElectionResult` model contains a `results_data` JSONB column with potentially large ballot result data. For search/filter queries that only need summary fields (name, date, district, status), loading full JSONB blobs wastes bandwidth and memory.

**Why it happens:**
The eager load was added because `build_detail_response()` accesses `election.result` for precinct counts (lines 660-661). The list response only needs `precincts_reporting` and `precincts_participating`, not the full `results_data` JSONB.

**How to avoid:**
1. Check whether `ElectionSummary` actually uses any data from the `result` relationship. If it only uses precinct counts, consider adding them as denormalized columns on the `Election` table or using a column-level load (load only specific columns from the relationship).
2. For v1.1, the election count is low enough (34+) that this is not a performance issue. Flag it as a future optimization.
3. If adding a `q` parameter increases query frequency significantly (public search endpoint), profile the response size with and without the eager load.

**Warning signs:**
- Search endpoint response payloads are unexpectedly large in network inspector
- Database query time for list/search exceeds 100ms despite small result sets

**Phase to address:**
Phase 2 (Text search) -- investigate during implementation. Optimize only if measurable.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| ILIKE `%term%` without trigram index | Zero migration, works immediately | Full table scan at scale | Acceptable until >1,000 elections; current count is ~34 |
| Hardcoded race_category mapping | Fast, no migration needed | Must update when new district_type values appear from imports | Acceptable if mapping is a single constant with startup warning for unmapped values |
| Unscoped filter-options | Simple single-query-per-dimension implementation | Cannot show per-filter counts or context-sensitive dropdowns | Acceptable for v1.1; scoped options already in backlog |
| `eligible_county` gaps in county filter | Ship county filter faster | Incomplete results for county-filtered queries | Acceptable with clear documentation in capabilities endpoint |
| Growing parameter list on `list_elections()` | No refactoring needed for existing code | 12+ parameters already, adding 3-4 more is unwieldy | Refactor to a `ElectionSearchParams` dataclass if total exceeds 15 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Existing `list_elections` service function | Adding new parameters to the already-12-parameter function signature without grouping | Group new search/filter params into a Pydantic model or dataclass (e.g., `ElectionFilterParams`) passed as a single argument |
| Existing E2E test suite (61 tests) | New search/filter tests depend on the single seeded election having specific field values | Verify the E2E `seed_database` fixture's election has values useful for testing (e.g., non-null `district_type`, `eligible_county`). Add seed data if needed |
| Existing `deleted_at IS NULL` filter | Forgetting soft-delete exclusion in new aggregation queries (`SELECT DISTINCT`) | The existing `list_elections` includes this. All `/filter-options` queries must also filter `WHERE deleted_at IS NULL` |
| OpenAPI contract tests | New query parameters and response models change the OpenAPI spec | Update `contracts/openapi.yaml` for every new parameter and endpoint; contract tests will catch drift |
| Existing pagination pattern | Inconsistent pagination on new endpoints (filter-options is not paginated but capabilities might be expected to be) | Capabilities and filter-options are single-response endpoints, not paginated. Only the list endpoint is paginated |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| ILIKE `%term%` OR on two columns | Slow text search response | Acceptable at current scale; add `pg_trgm` GIN index via Alembic migration if needed | >1,000 elections |
| `SELECT DISTINCT` for each filter dimension in filter-options | Filter-options endpoint >200ms | One query per dimension; add `Cache-Control: public, max-age=300` header | >10,000 elections or >5 dimensions |
| Separate COUNT query + data query per list request | Every paginated request = 2 DB round-trips | Existing pattern; acceptable at current scale | Not a concern for v1.1 |
| `selectinload(Election.result)` loading JSONB blobs on search | Large response payloads, high memory usage | Profile; consider column-level loading for precinct counts only | >100 elections with large result sets |
| No caching on capabilities endpoint | Static response regenerated on every request | Return hardcoded dict or cache in-memory; add `Cache-Control: public, max-age=3600` | High traffic (capabilities is called on every page load) |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| ILIKE wildcard characters in user input | `%` and `_` in search terms produce unexpected matches (not SQL injection, but data leakage) | Escape wildcards with `_escape_like()` helper before wrapping in `%...%` |
| Unbounded `SELECT DISTINCT` in filter-options | DoS if a column has unexpectedly high cardinality | `district_type` and `eligible_county` are low-cardinality; add `LIMIT 500` as safety cap |
| Race category mapping exposes internal column names | Information leakage about DB schema if raw `district_type` values are returned | Map to user-friendly category names ("Federal", "State") not raw values ("us_house", "state_senate") |
| Filter-options reveals soft-deleted data | Deleted elections' district_type/county values appear in dropdowns | All aggregation queries must include `WHERE deleted_at IS NULL` |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| County filter returns no statewide elections | User in "Bibb" county misses Governor race | Document limitation in capabilities; frontend can show disclaimer |
| Filter options include values with zero current elections | User selects "Municipal" but no municipal elections exist for the active date range | Filter-options should only return values with at least one matching non-deleted election |
| Case sensitivity mismatch on county filter | User sends `county=bibb` but DB has `eligible_county=BIBB` | Use case-insensitive comparison (ILIKE or `func.upper()`) for county filter |
| Empty search results give no feedback | User types "governer" (typo) and gets zero results with no explanation | Echo applied filters in the response metadata so frontend can display "No results for 'governer'" |
| `q` parameter searches district but `district` filter also exists | User confused about which to use for district-specific filtering | Document clearly: `q` is broad text search; `district` is targeted district filter |

## "Looks Done But Isn't" Checklist

- [ ] **Route ordering:** Verify `GET /elections/capabilities` returns 200, not 422 -- test with the full router mounted, not just the handler in isolation
- [ ] **Empty string handling:** Verify `q=""` and `county=""` are treated as "no filter" not "match empty strings" -- FastAPI converts empty query params to empty strings, not None
- [ ] **Race category "Other":** Elections with NULL or unmapped `district_type` values must be accessible -- either via a catch-all category or excluded with documentation
- [ ] **County case normalization:** `eligible_county` may store "BIBB", "Bibb", or "bibb" depending on import source -- verify case-insensitive matching
- [ ] **Soft-delete exclusion:** All `SELECT DISTINCT` queries in filter-options include `WHERE deleted_at IS NULL`
- [ ] **Wildcard escaping:** ILIKE search values escape `%` and `_` characters
- [ ] **E2E test coverage:** New endpoints have at least one E2E smoke test per CLAUDE.md requirements; negative filter tests return `{"items": [], "pagination": {"total": 0}}` not 500
- [ ] **OpenAPI spec updated:** `contracts/openapi.yaml` includes all new query parameters and endpoints
- [ ] **Capabilities response is stable:** Response shape will not change between phases -- define it completely in Phase 1, even if some filters are implemented later (mark as `"status": "planned"`)

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Route ordering (capabilities swallowed by `/{id}`) | LOW | Move route registration order in `elections.py`; no data migration |
| Race category mapping mismatch | LOW | Update the mapping constant; add startup warning query; no migration |
| County filter dropping elections | MEDIUM | Requires either backfilling `eligible_county` for SOS elections or implementing geospatial statewide logic (deferred) |
| LIKE wildcard characters in search | LOW | Add `_escape_like()` helper; apply to all ILIKE filter values |
| ILIKE performance at scale | LOW | `CREATE EXTENSION pg_trgm` + GIN index via Alembic migration; no app code change |
| Breaking existing filter contract | HIGH | Any change to existing `district` filter behavior breaks current consumers; must be backward-compatible from day one |
| Filter-options includes deleted data | LOW | Add `WHERE deleted_at IS NULL` to aggregation queries |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Route ordering | Phase 1 (Capabilities) | `GET /elections/capabilities` returns 200; E2E test confirms |
| Filter combination semantics | Phase 2 (Text search) | Test: `q=X&district=Y` returns AND-combined results; documented in capabilities |
| Wildcard escaping | Phase 2 (Text search) | Test: `q=100%25` does not match unrelated records |
| Race category mapping | Phase 3 (Race category) | Startup log shows no unmapped `district_type` values; mapping constant exists as single source of truth |
| County NULL gaps | Phase 4 (County filter) | Capabilities documents coverage limitation; filter-options county list matches actual DB values |
| County case sensitivity | Phase 4 (County filter) | Test: `county=bibb` matches election with `eligible_county=BIBB` |
| Soft-delete in aggregations | Phase 5 (Filter options) | All DISTINCT queries include `deleted_at IS NULL`; verified by test with soft-deleted seed data |
| Empty string parameters | Phase 2 (Text search) | Test: `q=` returns same results as no `q` parameter |
| Existing contract preservation | All phases | Existing E2E tests pass without modification after each phase |

## Sources

- Direct codebase analysis: `src/voter_api/api/v1/elections.py` (route registration order, existing filters)
- Direct codebase analysis: `src/voter_api/services/election_service.py` (query building pattern, `ilike()` usage at line 625, `selectinload` at line 616)
- Direct codebase analysis: `src/voter_api/models/election.py` (`district_type` as `String(50)`, `eligible_county` nullable, existing indexes)
- FastAPI route matching: static paths must be registered before parameterized paths on the same router (HIGH confidence, documented FastAPI behavior)
- PostgreSQL ILIKE: leading wildcard `%term%` cannot use B-tree indexes; `pg_trgm` GIN indexes required for indexed LIKE/ILIKE (HIGH confidence, PostgreSQL docs)
- SQLAlchemy `ilike()`: uses bound parameters, safe from SQL injection; wildcards `%` and `_` still functional in pattern (HIGH confidence, SQLAlchemy docs)
- `.planning/PROJECT.md`: documents known concerns about `eligible_county` gaps, statewide filtering deferral, district partial match preservation

---
*Pitfalls research for: v1.1 Election Search -- adding search/filter/discovery capabilities to existing election API*
*Researched: 2026-03-16*
