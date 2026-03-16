---
phase: 7
slug: search-and-filters
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest --cov=voter_api --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ tests/integration/test_api/test_election_filters_api.py -x -q`
- **After every plan wave:** Run `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | SRCH-02 | unit | `uv run pytest tests/unit/test_services/test_election_filters.py -x -k "escape"` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | FILT-01 | unit | `uv run pytest tests/unit/test_services/test_election_filters.py -x -k "race_category"` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | SRCH-01 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "test_q"` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | FILT-01 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "race_category"` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 1 | FILT-02 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "county"` | ❌ W0 | ⬜ pending |
| 07-01-06 | 01 | 1 | FILT-03 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "election_date"` | ❌ W0 | ⬜ pending |
| 07-01-07 | 01 | 1 | FILT-04 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "combined"` | ❌ W0 | ⬜ pending |
| 07-01-08 | 01 | 1 | INTG-02 | integration | `uv run pytest tests/integration/test_api/test_election_filters_api.py -x -k "backward"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_services/test_election_filters.py` — stubs for SRCH-02 (escape utility), FILT-01 (RACE_CATEGORY_MAP validation)
- [ ] `tests/integration/test_api/test_election_filters_api.py` — stubs for SRCH-01, SRCH-02, FILT-01, FILT-02, FILT-03, FILT-04, INTG-02

*Existing infrastructure covers framework and fixtures.*

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
