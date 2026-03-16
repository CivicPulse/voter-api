# Project Research Summary

**Project:** v1.1 Election Search — Search, Filter, and Discovery API
**Domain:** Civic data REST API — election list filtering and progressive discovery
**Researched:** 2026-03-16
**Confidence:** HIGH

## Executive Summary

This milestone adds search, filtering, and discovery capabilities to the existing elections list endpoint in a mature FastAPI + SQLAlchemy async + PostgreSQL/PostGIS codebase. The scope is deliberately narrow: no new dependencies, no schema migrations, no new service files. Every required technology (ILIKE queries, DISTINCT aggregations, Pydantic response models, FastAPI query params) already exists in the codebase and follows well-established patterns. The recommended approach is purely additive — extend the existing `list_elections` filter builder, add a `get_filter_options()` service function, and register two new static endpoints on the elections router.

The key strategic recommendation is to build in dependency order: capabilities endpoint first (establishes the progressive discovery contract with zero risk), then all four search/filter extensions to `list_elections` together, then the filter-options endpoint last (since it depends on the race category mapping defined in phase 2). The capabilities endpoint is both the lowest-risk first step and the most immediately valuable for the frontend team, which needs it to know what filters to render.

The primary risks are operational rather than architectural: FastAPI route ordering (static paths must precede `/{election_id}` or they get swallowed as UUID params), race category mapping drift as new `district_type` values arrive via import pipelines, and the `eligible_county` NULL gap that causes county-filtered results to silently omit statewide elections. All three are well-understood and preventable with specific implementation steps documented in the research.

## Key Findings

### Recommended Stack

No new dependencies are required. The existing stack covers every feature: PostgreSQL ILIKE for text search, SQLAlchemy `func.distinct()` and `func.count()` for filter options aggregation, Pydantic v2 for new response schemas, and FastAPI Query params for new filter parameters. The research explicitly recommends against PostgreSQL full-text search (tsvector/GIN) and external search engines — ILIKE with OR on two columns is adequate for the current ~34-election dataset and will remain adequate up to ~1,000 elections.

**Core technologies:**
- PostgreSQL 15 / PostGIS 3.4: ILIKE, DISTINCT, COUNT aggregation — all built-in, no extensions needed at current scale
- SQLAlchemy 2.x async: `.ilike()`, `func.count()`, `func.distinct()`, `or_()` — all already in use in `election_service.py`
- FastAPI: new Query params and endpoint functions — zero additional configuration
- Pydantic v2: new `CapabilitiesResponse`, `FilterOptionsResponse`, `RACE_CATEGORY_MAP` constant — follows existing schema patterns

### Expected Features

**Must have (table stakes) — frontend team is blocked without these:**
- Text search (`q` param) — ILIKE on `name` + `district` columns; highest user-facing value
- Race category filter (`race_category`) — maps frontend buckets (federal/state/county) to `district_type` values; column and indexes already exist
- County filter (`county`) — exact case-insensitive match on `eligible_county`; column and index already exist
- Exact date filter (`election_date`) — equality on `election_date`; column and index already exist
- Filter options endpoint (`GET /elections/filter-options`) — returns distinct valid values for each filter dimension

**Should have (competitive differentiators):**
- Capabilities endpoint (`GET /elections/capabilities`) — progressive discovery; tells the frontend what filters exist and their semantics; no other civic data API exposes this
- Combined multi-filter queries — already works via the AND filter chain; composable GET params are a genuine differentiator vs. address-centric APIs like Google Civic and BallotReady

**Defer (v1.x after validation):**
- Scoped/cascading filter options — combinatorial query complexity; unscoped is correct for v1.1
- Multi-value comma-separated filters — add when the frontend requests multi-select dropdowns
- `pg_trgm` trigram index — add only when election count exceeds ~500

**Defer (v2+):**
- Address-based "my elections" lookup — different product feature, not a list filter
- Full-text search with ranking — only if dataset grows dramatically
- Statewide election inclusion in county filter — requires geospatial boundary joins; already deferred in PROJECT.md

### Architecture Approach

Extend the existing elections vertical rather than creating new files. All changes land in three existing files (`schemas/election.py`, `services/election_service.py`, `api/v1/elections.py`) plus E2E tests. The `list_elections` filter builder pattern (accumulating `list[ColumnElement[bool]]` then combining with `and_(*filters)`) is the correct extension point for all four new filters. Two new endpoint functions are added to the same elections router, registered before the `/{election_id}` route. Zero Alembic migrations, zero new service files, zero new dependencies.

**Major components:**
1. `schemas/election.py` — add `RACE_CATEGORY_MAP` constant, `CapabilitiesResponse`, `FilterOptionsResponse` schemas
2. `services/election_service.py` — extend `list_elections()` with 4 new filter params; add `get_filter_options()` aggregation function
3. `api/v1/elections.py` — add 4 Query params to `list_elections` handler; add `GET /capabilities` and `GET /filter-options` endpoints (inserted before `/{election_id}`)

### Critical Pitfalls

1. **FastAPI route ordering** — `GET /elections/capabilities` must be registered before `GET /elections/{election_id}` or FastAPI parses "capabilities" as a UUID and returns 422. Insert both new endpoints between the `POST /import-feed` block and `GET /{election_id}`. Verify with E2E test on the full mounted router, not the handler in isolation.

2. **Race category mapping drift** — `district_type` is a free-form `String(50)` column, not a DB enum. New import pipelines can introduce values not in the mapping, silently dropping elections from filtered results. Define `RACE_CATEGORY_MAP` as a single constant, add a startup/health-check query to warn on unmapped values, and expose the mapping in the capabilities endpoint.

3. **`eligible_county` NULL gap** — Many elections have no `eligible_county` (SOS feed elections, manually created elections). County filter correctly omits them — this is intentional v1.1 behavior. Document the limitation in the capabilities response so the frontend can show a disclaimer. Do not attempt statewide inclusion in this milestone.

4. **ILIKE wildcard characters in user input** — `%` and `_` in `q` values are SQL wildcards that produce unexpected matches (not injection, but incorrect results). Apply an `_escape_like()` helper (escape `\`, `%`, `_`) to all ILIKE filter values before wrapping with `%...%`. Apply to the existing `district` filter too.

5. **AsyncSession concurrency on filter-options** — The three DISTINCT queries in `get_filter_options()` must run sequentially on the same `AsyncSession`. Using `asyncio.gather` with the same session raises `MissingGreenlet` or produces undefined behavior. Sequential `await session.execute()` calls are correct and sufficient at this data scale.

## Implications for Roadmap

Based on research, a three-phase build order is recommended. The phases follow dependency order, minimize risk, and deliver value incrementally to the frontend team.

### Phase 1: Capabilities Endpoint

**Rationale:** Zero dependencies, zero DB interaction, zero risk. Establishes the progressive discovery pattern that the frontend team needs immediately to know what filters to render. Building this first also forces the complete capabilities schema to be defined upfront, which prevents the response shape from changing mid-milestone.

**Delivers:** `GET /elections/capabilities` returning a static, versioned JSON contract listing all supported filters, search fields, and sort options.

**Addresses:** Capabilities progressive discovery feature (competitive differentiator); route ordering requirement.

**Avoids:** Route ordering pitfall — establishing the correct insertion point before `/{election_id}` before any other new endpoints are added.

### Phase 2: Search and Filter Extensions

**Rationale:** Four independent filter additions to a single existing function. Build them together to define the `RACE_CATEGORY_MAP` constant once and apply it consistently. Text search (`q`) is the highest user-facing value and sets the implementation pattern (ILIKE, wildcard escaping) that all other ILIKE filters follow.

**Delivers:** `?q=`, `?race_category=`, `?county=`, `?election_date=` filter parameters on `GET /elections`. ILIKE wildcard escaping applied to all string filters including the existing `district` param.

**Addresses:** All four table-stakes filter features. Filter combination semantics documented.

**Avoids:** Wildcard character pitfall (escape helper defined here); empty string handling; preserving existing filter contract for current API consumers.

**Build sub-order within phase:** `q` (ILIKE pattern + wildcard escaping) → `election_date` (trivial equality) → `county` (case-insensitive exact match) → `race_category` (mapping dict + IN clause).

### Phase 3: Filter Options Endpoint

**Rationale:** Must be built last because it depends on `RACE_CATEGORY_MAP` from Phase 2 to reverse-map `district_type` values to frontend categories. This endpoint is the discovery mechanism that makes the Phase 2 filters usable — frontend dropdowns need to know what values currently exist in the data.

**Delivers:** `GET /elections/filter-options` returning distinct valid values for race categories, counties, and election dates derived from live data.

**Addresses:** Filter options table-stakes feature; completes the capabilities contract started in Phase 1.

**Avoids:** Soft-delete exclusion in aggregations (all DISTINCT queries filter `deleted_at IS NULL`); filter-options returning values with zero matching elections; AsyncSession concurrency (sequential queries only).

### Phase Ordering Rationale

- Phase 1 first because it has zero dependencies, delivers immediate frontend value, and establishes the route insertion point that all subsequent endpoints must respect.
- Phase 2 before Phase 3 because the `RACE_CATEGORY_MAP` constant defined in Phase 2 is a prerequisite for the reverse-mapping logic in Phase 3's filter-options service function.
- E2E tests are written incrementally with each phase, not batched at the end. The existing 61-test E2E suite must continue to pass after every phase merge.
- OpenAPI contract (`contracts/openapi.yaml`) must be updated in the same phase as each new endpoint or parameter — contract tests will fail if deferred.

### Research Flags

Phases with standard patterns (research not needed):
- **Phase 1 (Capabilities):** Static Pydantic response model. No database, no business logic. Well-documented FastAPI pattern.
- **Phase 2 (Filters):** ILIKE filter builder extension. Follows existing codebase pattern exactly. Multiple prior examples in `voter_service.py` and `meeting_search_service.py`.
- **Phase 3 (Filter Options):** SQLAlchemy DISTINCT aggregation queries. Standard SQL pattern, already used throughout the codebase.

No phase requires a `/gsd:research-phase` call. All patterns are either already implemented in this codebase or are straightforward PostgreSQL/SQLAlchemy patterns with HIGH confidence documentation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Based on direct codebase inspection. All required APIs already in use. No new packages. |
| Features | HIGH | Frontend requirements are known (voter-web team). Competitor analysis confirms CivPulse's browsable model is differentiated. Scope is unambiguous. |
| Architecture | HIGH | Based on direct inspection of `election_service.py` lines 581-660, `elections.py` route order, and existing model columns/indexes. Integration points are concrete. |
| Pitfalls | HIGH | Route ordering is confirmed FastAPI behavior. Wildcard escaping is documented SQLAlchemy/PostgreSQL behavior. NULL gaps are confirmed by PROJECT.md acknowledgment. |

**Overall confidence:** HIGH

### Gaps to Address

- **`eligible_county` data coverage:** How many elections currently have a non-null `eligible_county`? Run `SELECT COUNT(*), COUNT(eligible_county) FROM elections WHERE deleted_at IS NULL` before writing filter-options to understand actual coverage. This affects whether county filter-options will return useful values at all.

- **`district_type` value inventory:** The `RACE_CATEGORY_MAP` must cover all values currently in the database. Run `SELECT DISTINCT district_type FROM elections WHERE deleted_at IS NULL ORDER BY district_type` before defining the mapping to ensure no existing elections are missed by the filter.

- **E2E seed data adequacy:** The single seeded election in `conftest.py` may not have `eligible_county` or `district_type` populated. Verify before Phase 2 testing and add seed data if needed (per CLAUDE.md E2E test update rules — use a fixed UUID constant and `on_conflict_do_update` for idempotency).

## Sources

### Primary (HIGH confidence — direct codebase inspection)
- `src/voter_api/services/election_service.py` lines 581-695 — existing filter builder pattern, ILIKE usage, selectinload
- `src/voter_api/api/v1/elections.py` — route registration order confirming `/{election_id}` at line 171
- `src/voter_api/models/election.py` lines 37-126 — all existing columns and indexes
- `src/voter_api/services/voter_service.py` lines 82-89 — existing ILIKE wildcard-escape pattern
- `.planning/PROJECT.md` — milestone scope, explicit deferrals, key design decisions

### Primary (HIGH confidence — official documentation)
- FastAPI route matching documentation — static paths matched before path parameter routes in declaration order
- SQLAlchemy 2.x async documentation — AsyncSession is not safe for concurrent queries
- PostgreSQL documentation — ILIKE with `%term%` cannot use B-tree indexes; `pg_trgm` required for indexed LIKE at scale

### Secondary (MEDIUM confidence — comparative analysis)
- Google Civic Information API — address-centric model, no list/filter endpoints
- BallotReady API — GraphQL, address/lat-lon model, government level filter
- Democracy Works Elections API — OCD-ID based filtering
- Speakeasy REST API filtering best practices — query parameter design patterns
- Moesif REST API Design: Filtering, Sorting, Pagination — filter design patterns

---
*Research completed: 2026-03-16*
*Ready for roadmap: yes*
