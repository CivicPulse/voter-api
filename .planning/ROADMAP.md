# Roadmap: CivPulse Voter API

## Milestones

- **v1.0 Better Imports** - Phases 1-5 (shipped 2026-03-15)
- **v1.1 Election Search** - Phases 6-8 (in progress)

## Phases

<details>
<summary>v1.0 Better Imports (Phases 1-5) - SHIPPED 2026-03-15</summary>

- [x] Phase 1: Data Contracts (3/3 plans) - completed 2026-03-14
- [x] Phase 2: Converter and Import Pipeline (3/3 plans) - completed 2026-03-15
- [x] Phase 3: Claude Code Skills (5/5 plans) - completed 2026-03-15
- [x] Phase 4: End-to-End Demo (2/2 plans) - completed 2026-03-15
- [x] Phase 5: Milestone Cleanup & Traceability (2/2 plans) - completed 2026-03-15

</details>

### v1.1 Election Search

- [ ] **Phase 6: Capabilities Discovery** - Static capabilities endpoint establishing route ordering and progressive discovery contract
- [ ] **Phase 7: Search and Filters** - Free-text search, race category, county, and date filters on the elections list endpoint
- [ ] **Phase 8: Filter Options and E2E** - Dynamic filter-options endpoint and comprehensive E2E test coverage

## Phase Details

### Phase 6: Capabilities Discovery
**Goal**: API consumers can discover what search and filter parameters the elections API supports
**Depends on**: Nothing (first phase of v1.1; builds on existing elections router from v1.0)
**Requirements**: DISC-01, INTG-01
**Success Criteria** (what must be TRUE):
  1. `GET /api/v1/elections/capabilities` returns a JSON response listing all supported filter parameters, search fields, and their semantics
  2. The capabilities endpoint responds correctly at `/elections/capabilities` without being swallowed by the `/{election_id}` path parameter route (route ordering is correct)
  3. All existing election endpoints continue to work identically after the new route is added
**Plans**: 1 plan

Plans:
- [ ] 06-01: Capabilities endpoint with route ordering

### Phase 7: Search and Filters
**Goal**: Users can search and filter the elections list by text, race category, county, and exact date
**Depends on**: Phase 6 (route ordering established)
**Requirements**: SRCH-01, SRCH-02, FILT-01, FILT-02, FILT-03, FILT-04, INTG-02
**Success Criteria** (what must be TRUE):
  1. `GET /api/v1/elections?q=primary` returns elections whose name or district contains "primary" (case-insensitive partial match)
  2. Special characters in the `q` parameter (e.g., `%`, `_`) are treated as literal text, not as SQL wildcards
  3. `GET /api/v1/elections?race_category=federal` returns only elections whose `district_type` maps to the federal category; invalid category values return a validation error
  4. `GET /api/v1/elections?county=Bibb` returns elections with matching `eligible_county` (case-insensitive); `?election_date=2026-05-19` returns elections on that exact date
  5. All new filters combine with each other and with existing filters (`district`, `date_from`, `date_to`, `status`) using AND logic; omitting all new params returns the same results as before
**Plans**: 2 plans

Plans:
- [ ] 07-01-PLAN.md — Service layer filter logic, escape utility, route handler params, and unit tests
- [ ] 07-02-PLAN.md — Integration tests for all search and filter parameters

### Phase 8: Filter Options and E2E
**Goal**: API consumers can fetch valid filter values for dynamic dropdowns, and all new functionality has E2E test coverage
**Depends on**: Phase 7 (RACE_CATEGORY_MAP and filter logic defined)
**Requirements**: DISC-02, INTG-03
**Success Criteria** (what must be TRUE):
  1. `GET /api/v1/elections/filter-options` returns distinct valid values for race categories, counties, and election dates derived from live database data
  2. Filter-options response excludes soft-deleted elections and only returns values that have at least one matching election
  3. E2E tests cover all three new endpoints (`/capabilities`, filter params `q`/`race_category`/`county`/`election_date`, `/filter-options`) with seed data that exercises `eligible_county` and `district_type` fields
  4. All existing E2E tests continue to pass alongside the new tests
**Plans**: TBD

Plans:
- [ ] 08-01: Filter options endpoint and E2E tests

## Progress

**Execution Order:**
Phases execute in numeric order: 6 -> 7 -> 8

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Data Contracts | v1.0 | 3/3 | Complete | 2026-03-14 |
| 2. Converter and Import Pipeline | v1.0 | 3/3 | Complete | 2026-03-15 |
| 3. Claude Code Skills | v1.0 | 5/5 | Complete | 2026-03-15 |
| 4. End-to-End Demo | v1.0 | 2/2 | Complete | 2026-03-15 |
| 5. Milestone Cleanup | v1.0 | 2/2 | Complete | 2026-03-15 |
| 6. Capabilities Discovery | v1.1 | 0/1 | Not started | - |
| 7. Search and Filters | v1.1 | 0/2 | Not started | - |
| 8. Filter Options and E2E | v1.1 | 0/1 | Not started | - |
