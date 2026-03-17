# Phase 10: Fix Mismatch Filter SQL Defect - Context

**Gathered:** 2026-03-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the structural SQL defect in `_build_mismatch_filter()` where ORM column references (`AnalysisResult.mismatch_details`) cause an implicit cross join to the `analysis_results` table, bypassing the `DISTINCT ON` deduplication in the `latest_ar` subquery. Harden tests to assert compiled SQL correctness and add a GIN index on `mismatch_details` for JSONB containment query performance.

</domain>

<decisions>
## Implementation Decisions

### Function Signature Change
- Pass `latest_ar` (Subquery) as the first parameter to `_build_mismatch_filter(latest_ar, district_type, has_district_mismatch)`
- Use `latest_ar.c.mismatch_details` instead of `AnalysisResult.mismatch_details` throughout the function
- `_apply_voter_filters` also receives `latest_ar` as a parameter — the caller (`list_election_participants`) already creates it for the JOIN, so pass it through. No second subquery instance.
- Single source of truth: the same `latest_ar` alias used in the JOIN is used in the WHERE clause

### Test Hardening Strategy
- **Compile-and-assert-FROM**: Unit tests compile the full query (with JOINs) to SQL via `literal_compile` with PostgreSQL dialect, then assert `FROM analysis_results` does NOT appear outside the subquery and `latest_ar` IS present
- **Replace weak tests**: Delete existing `isinstance(ClauseElement)` checks — the compile-and-assert tests are strictly stronger
- **E2E multi-run deduplication test**: Seed a voter with 2+ analysis results (different timestamps), one with mismatch and one without. Assert the filter uses only the latest result. Directly tests the DISTINCT ON deduplication path.

### GIN Index
- Add a GIN index on `analysis_results.mismatch_details` via Alembic migration in this phase
- Full GIN (not partial) — simple, standard, covers all `@>` containment queries
- Closes the tech debt item flagged in the milestone audit

### Claude's Discretion
- Exact Alembic migration structure for the GIN index
- Test helper organization (inline vs extracted fixtures)
- Which specific assertions to include in the E2E deduplication test beyond voter identity
- Error message wording adjustments if any

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Defect documentation
- `.planning/v1.2-MILESTONE-AUDIT.md` — Full defect analysis, fix guidance (6-step plan), tech debt items, and E2E flow status

### Code to fix
- `src/voter_api/services/voter_history_service.py` — Lines 690-711 (`_build_mismatch_filter`), lines 714-766 (`_apply_voter_filters`), lines 600-620 (`list_election_participants` JOIN setup), line 870 (correct pattern in stats path)

### Tests to harden
- `tests/unit/test_services/test_voter_history_service.py` — Existing weak `isinstance(ClauseElement)` tests to replace
- `tests/e2e/test_smoke.py` — E2E test classes for participation endpoints
- `tests/e2e/conftest.py` — Seed fixtures for E2E (add multi-run analysis data)

### Phase 9 context (prior decisions)
- `.planning/phases/09-context-aware-mismatch-filter/09-CONTEXT.md` — JSONB containment operator choice, `latest_ar` subquery pattern, `MismatchFilterError` design

### Data model
- `src/voter_api/models/analysis_result.py` — `AnalysisResult` model with `mismatch_details` JSONB column

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_latest_analysis_subquery()` (line 674-684): Already creates the DISTINCT ON subquery — just needs to be passed through to the filter function
- Stats path at line 870: Reference implementation showing correct `latest_ar.c.mismatch_details` usage
- `type_coerce(target_value, JSONB_TYPE)`: Existing JSONB type coercion pattern

### Established Patterns
- **Subquery alias pattern**: `_latest_analysis_subquery()` returns `.subquery("latest_ar")` — standard SQLAlchemy subquery aliasing
- **Filter function pattern**: `_build_mismatch_filter` and `_apply_voter_filters` are private helpers — changing signatures is internal-only, no API impact
- **E2E seed pattern**: `conftest.py` uses `on_conflict_do_update` with fixed UUIDs for idempotent seeding

### Integration Points
- `_apply_voter_filters` line 761-764: Call site where `_build_mismatch_filter` is invoked — needs `latest_ar` parameter added
- `list_election_participants` line 603: Where `latest_ar` is created — pass to `_apply_voter_filters`
- Alembic migrations: Next migration number after current head (for GIN index)

</code_context>

<specifics>
## Specific Ideas

- The stats path (line 870) is the "known good" reference — the fix should make the list path match that pattern exactly
- Both `=true` and `=false` paths in `_build_mismatch_filter` need fixing (lines 704 and 708-710)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-fix-mismatch-filter-sql-defect*
*Context gathered: 2026-03-16*
