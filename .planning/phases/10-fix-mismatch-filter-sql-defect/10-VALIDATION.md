---
phase: 10
slug: fix-mismatch-filter-sql-defect
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-16
validated: 2026-03-17
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `uv run pytest tests/unit/test_services/test_voter_history_service.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_services/test_voter_history_service.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | MISMATCH-01 | lint + code | `uv run ruff check src/voter_api/services/voter_history_service.py` | ✅ | ✅ green |
| 10-01-02 | 01 | 1 | MISMATCH-01 | unit (compile-and-assert) | `uv run pytest tests/unit/test_services/test_voter_history_service.py::TestBuildMismatchFilter -x` | ✅ (5 tests) | ✅ green |
| 10-01-03 | 01 | 1 | MISMATCH-01 | e2e + migration | `uv run pytest tests/e2e/ --collect-only` | ✅ (189 tests collected) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `alembic/versions/030_add_gin_index_analysis_results_mismatch_details.py` — GIN index migration for MISMATCH-01
- [x] New compile-and-assert tests in `tests/unit/test_services/test_voter_history_service.py::TestBuildMismatchFilter`
- [x] New E2E deduplication test in `tests/e2e/test_smoke.py::TestVoterHistory`
- [x] New `AnalysisRun` + `AnalysisResult` seed rows in `tests/e2e/conftest.py`

*Existing infrastructure covers test framework and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ✅ validated 2026-03-17

---

## Validation Audit 2026-03-17

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
