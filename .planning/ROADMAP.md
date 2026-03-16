# Roadmap: CivPulse Voter API

## Milestones

- ✅ **v1.0 Better Imports** — Phases 1-5 (shipped 2026-03-15)
- ✅ **v1.1 Election Search** — Phases 6-8 (shipped 2026-03-16)
- 🚧 **v1.2 Context-Aware District Mismatch** — Phase 9 (in progress)

## Phases

<details>
<summary>✅ v1.0 Better Imports (Phases 1-5) — SHIPPED 2026-03-15</summary>

- [x] Phase 1: Data Contracts (3/3 plans) — completed 2026-03-14
- [x] Phase 2: Converter and Import Pipeline (3/3 plans) — completed 2026-03-15
- [x] Phase 3: Claude Code Skills (5/5 plans) — completed 2026-03-15
- [x] Phase 4: End-to-End Demo (2/2 plans) — completed 2026-03-15
- [x] Phase 5: Milestone Cleanup & Traceability (2/2 plans) — completed 2026-03-15

</details>

<details>
<summary>✅ v1.1 Election Search (Phases 6-8) — SHIPPED 2026-03-16</summary>

- [x] Phase 6: Capabilities Discovery (1/1 plans) — completed 2026-03-16
- [x] Phase 7: Search and Filters (2/2 plans) — completed 2026-03-16
- [x] Phase 8: Filter Options and E2E (2/2 plans) — completed 2026-03-16

</details>

### v1.2 Context-Aware District Mismatch (In Progress)

**Milestone Goal:** When filtering election participation by `has_district_mismatch`, only flag voters whose mismatch is on the district type relevant to that specific election.

- [x] **Phase 9: Context-Aware Mismatch Filter** - Scope `has_district_mismatch` on the participation endpoint to the election's own `district_type` via `analysis_results` JSONB lookup (completed 2026-03-16)
- [x] **Phase 10: Fix Mismatch Filter SQL Defect** - Fix ORM column reference in `_build_mismatch_filter` to use subquery alias, harden tests for compiled SQL correctness (completed 2026-03-16)

## Phase Details

### Phase 9: Context-Aware Mismatch Filter
**Goal**: API callers can filter election participation by district mismatch scoped to the election's own district type — not a blanket mismatch flag across all district types
**Depends on**: Phase 8
**Requirements**: MISMATCH-01
**Success Criteria** (what must be TRUE):
  1. `GET /elections/{id}/participation?has_district_mismatch=true` returns only voters who have a mismatch on that election's `district_type` (looked up from `analysis_results.mismatch_details` JSONB)
  2. Voters with mismatches on a different district type than the election's are excluded from `has_district_mismatch=true` results
  3. `has_district_mismatch=false` and omitting the filter entirely continue to return correct voter sets without regression
  4. The filter behaves correctly across elections with different district types (e.g., `state_senate`, `county_commission`, `us_house`)
**Plans:** 2/2 plans complete

Plans:
- [ ] 09-01-PLAN.md — Implement context-aware JSONB mismatch filter in service layer, schemas, and route handler
- [ ] 09-02-PLAN.md — Add unit, integration, and E2E tests for mismatch filter

### Phase 10: Fix Mismatch Filter SQL Defect
**Goal**: Fix the structural SQL defect in `_build_mismatch_filter()` where ORM column references cause an implicit cross join, and harden tests to assert compiled SQL correctness
**Depends on**: Phase 9
**Requirements**: MISMATCH-01
**Gap Closure:** Closes gaps from audit (v1.2-MILESTONE-AUDIT.md)
**Plans:** 1/1 plans complete
**Success Criteria** (what must be TRUE):
  1. `_build_mismatch_filter()` uses `latest_ar.c.mismatch_details` (subquery alias) instead of `AnalysisResult.mismatch_details` (ORM column)
  2. Compiled SQL for participation queries contains no implicit `FROM analysis_results` — only the `DISTINCT ON` subquery alias
  3. Unit tests compile the full query in joined context and assert correct FROM clauses
  4. E2E test with multiple analysis runs per voter verifies deduplication (only latest analysis result used)

Plans:
- [ ] 10-01-PLAN.md — Fix SQL defect, compile-and-assert unit tests, E2E deduplication test, GIN index migration

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Data Contracts | v1.0 | 3/3 | Complete | 2026-03-14 |
| 2. Converter and Import Pipeline | v1.0 | 3/3 | Complete | 2026-03-15 |
| 3. Claude Code Skills | v1.0 | 5/5 | Complete | 2026-03-15 |
| 4. End-to-End Demo | v1.0 | 2/2 | Complete | 2026-03-15 |
| 5. Milestone Cleanup | v1.0 | 2/2 | Complete | 2026-03-15 |
| 6. Capabilities Discovery | v1.1 | 1/1 | Complete | 2026-03-16 |
| 7. Search and Filters | v1.1 | 2/2 | Complete | 2026-03-16 |
| 8. Filter Options and E2E | v1.1 | 2/2 | Complete | 2026-03-16 |
| 9. Context-Aware Mismatch Filter | v1.2 | 2/2 | Complete | 2026-03-16 |
| 10. Fix Mismatch Filter SQL Defect | 1/1 | Complete    | 2026-03-16 | - |
