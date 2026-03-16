---
phase: 10-fix-mismatch-filter-sql-defect
verified: 2026-03-16T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 10: Fix Mismatch Filter SQL Defect — Verification Report

**Phase Goal:** Fix the structural SQL defect in `_build_mismatch_filter()` where ORM column references cause an implicit cross join, and harden tests to assert compiled SQL correctness
**Verified:** 2026-03-16
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | `_build_mismatch_filter` uses `latest_ar.c.mismatch_details` (subquery alias) not `AnalysisResult.mismatch_details` (ORM column) | VERIFIED | Lines 707, 712, 713 of `voter_history_service.py` use `latest_ar.c.mismatch_details`; grep for `AnalysisResult.mismatch_details` returns zero hits in the service file |
| 2 | Compiled SQL for participation queries contains no implicit FROM `analysis_results` outside the DISTINCT ON subquery | VERIFIED | 5 compile-and-assert tests pass (`TestBuildMismatchFilter`); `test_no_duplicate_from_analysis_results` asserts `"from analysis_results"` appears exactly once |
| 3 | Unit tests compile the full joined query and assert correct FROM clauses | VERIFIED | `TestBuildMismatchFilter` class (5 tests) uses `_compile_query(postgresql.dialect())` and asserts `"latest_ar" in sql` and `"analysis_results" not in where_portion`; all 5 pass |
| 4 | E2E test with multiple analysis runs per voter verifies only the latest result is used | VERIFIED | `test_participation_mismatch_deduplication_latest_result_used` exists in `TestVoterHistory`; collected by `pytest --collect-only`; seed data has two `AnalysisResult` rows (old: mismatch, new: match) |
| 5 | GIN index `ix_result_mismatch_details_gin` exists on `analysis_results.mismatch_details` | VERIFIED | `030_add_gin_index_analysis_results_mismatch_details.py` creates `ix_result_mismatch_details_gin` with `postgresql_using="gin"`; `alembic heads` shows this as sole head; `down_revision = "f4b2c6d9e013"` is correct |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/voter_api/services/voter_history_service.py` | Fixed `_build_mismatch_filter` and `_apply_voter_filters` with `latest_ar` parameter | VERIFIED | `_build_mismatch_filter(latest_ar: Any, ...)` at line 689; `_apply_voter_filters(..., latest_ar: Any = None)` at line 717; three `latest_ar.c.mismatch_details` references in filter path |
| `tests/unit/test_services/test_voter_history_service.py` | Compile-and-assert SQL correctness tests | VERIFIED | `_compile_query` helper at line 41; `TestBuildMismatchFilter` class at line 476 with 5 compile-and-assert tests; all pass |
| `tests/e2e/conftest.py` | Multi-run analysis seed data for deduplication test | VERIFIED | Six UUID constants added; `AnalysisRun` and `AnalysisResult` imports present; two analysis result rows seeded (old with mismatch, new without); teardown cleanup present |
| `tests/e2e/test_smoke.py` | E2E deduplication test | VERIFIED | `test_participation_mismatch_deduplication_latest_result_used` at line 1868; `ELECTION_STATE_SENATE_FULTON_ID` imported at line 26 |
| `alembic/versions/030_add_gin_index_analysis_results_mismatch_details.py` | GIN index migration | VERIFIED | `ix_result_mismatch_details_gin`, `postgresql_using="gin"`, `down_revision = "f4b2c6d9e013"` all present; sole Alembic head confirmed |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `list_election_participants` | `_apply_voter_filters` | `latest_ar=latest_ar if mismatch_filter_active else None` | WIRED | Line 647 of `voter_history_service.py` passes `latest_ar` conditionally |
| `_apply_voter_filters` | `_build_mismatch_filter` | `_build_mismatch_filter(latest_ar, district_type, ...)` | WIRED | Line 767 calls with `latest_ar` as first arg; guard at line 766 requires `latest_ar is not None` |
| `_build_mismatch_filter` | `latest_ar` subquery alias | `latest_ar.c.mismatch_details` | WIRED | Lines 707, 712, 713 reference `latest_ar.c.mismatch_details` exclusively; no ORM column reference present |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| MISMATCH-01 | 10-01-PLAN.md | Participation endpoint `has_district_mismatch=true` only returns voters whose mismatch is on the election's `district_type` (via `analysis_results.mismatch_details` JSONB lookup) | SATISFIED | SQL defect fixed: `_build_mismatch_filter` now references `latest_ar.c.mismatch_details` exclusively, preventing implicit cross join. Compile-and-assert unit tests verify FROM clause structure. E2E deduplication test verifies correct latest-result-wins behavior. GIN index enables efficient JSONB `@>` queries. |

No orphaned requirements — REQUIREMENTS.md maps only MISMATCH-01 to Phase 10, and the plan claims MISMATCH-01. Full coverage.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `alembic/versions/030_normalize_voter_registration_numbers.py` | 24-25 | Stale orphaned migration file with `revision="030"` / `down_revision="029"` — not in active chain | INFO | No runtime impact. `alembic heads` returns a single head (`030_gin_mismatch_details`). The orphan is unreachable in the current chain (`029 → f4b2c6d9e013 → 030_gin_mismatch_details`). Naming collision with the active `030_` prefix migration could cause confusion. |

The orphaned migration file is a pre-existing artifact from an earlier dev branch, not introduced by this phase. It does not block the goal.

### Human Verification Required

#### 1. E2E Deduplication Test Runtime Behavior

**Test:** Run `uv run pytest tests/e2e/test_smoke.py::TestVoterHistory::test_participation_mismatch_deduplication_latest_result_used -v` against a live PostGIS database with migrations applied including `030_gin_mismatch_details`.
**Expected:** Test passes — voter `E2E000001` absent from `has_district_mismatch=true` results and present in `has_district_mismatch=false` results.
**Why human:** E2E tests require a running PostGIS database; automated verification confirmed collection only.

#### 2. GIN Index Applied to Database

**Test:** After running `alembic upgrade head`, query `pg_indexes` to confirm `ix_result_mismatch_details_gin` exists on `analysis_results`.
**Expected:** `SELECT indexname FROM pg_indexes WHERE tablename = 'analysis_results' AND indexname = 'ix_result_mismatch_details_gin';` returns one row.
**Why human:** Index existence in the live database cannot be verified without a PostGIS connection.

### Gaps Summary

No gaps. All five must-have truths are fully verified. The only notable finding is a pre-existing orphaned migration file (`030_normalize_voter_registration_numbers.py`) that is unreachable in the active Alembic chain and was not introduced by this phase.

**Commits verified:** f398a96 (fix), 3da454a (test), df876cb (style), c1200b3 (feat) — all exist in git history.

**Test results:** 2355 unit tests pass, 3 skipped, 0 failures. All 5 `TestBuildMismatchFilter` compile-and-assert tests pass. E2E test collects successfully.

**Lint:** Zero ruff violations across all phase-modified files.

---

_Verified: 2026-03-16_
_Verifier: Claude (gsd-verifier)_
