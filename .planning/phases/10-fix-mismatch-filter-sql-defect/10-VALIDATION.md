---
phase: 10
slug: fix-mismatch-filter-sql-defect
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
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
| 10-01-01 | 01 | 1 | MISMATCH-01 | unit (compile-and-assert) | `uv run pytest tests/unit/test_services/test_voter_history_service.py::TestBuildMismatchFilter -x` | ✅ (class exists, tests need replacement) | ⬜ pending |
| 10-01-02 | 01 | 1 | MISMATCH-01 | e2e | `uv run pytest tests/e2e/test_smoke.py::TestVoterHistory -x` | ✅ (class exists, new test needed) | ⬜ pending |
| 10-01-03 | 01 | 1 | MISMATCH-01 | migration | `uv run voter-api db upgrade` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `alembic/versions/<rev>_add_gin_index_analysis_results_mismatch_details.py` — GIN index migration for MISMATCH-01
- [ ] New compile-and-assert tests in `tests/unit/test_services/test_voter_history_service.py::TestBuildMismatchFilter`
- [ ] New E2E deduplication test in `tests/e2e/test_smoke.py::TestVoterHistory`
- [ ] New `AnalysisRun` + `AnalysisResult` seed rows in `tests/e2e/conftest.py`

*Existing infrastructure covers test framework and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
