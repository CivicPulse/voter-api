---
phase: 8
slug: filter-options-and-e2e
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/e2e/ -x -k "filter_options or capabilities or search"` |
| **Full suite command** | `uv run pytest tests/e2e/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/e2e/ --collect-only`
- **After every plan wave:** Run `uv run pytest tests/e2e/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | DISC-02 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "filter_options"` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | DISC-02 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "soft_deleted"` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 1 | DISC-02 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "cache"` | ❌ W0 | ⬜ pending |
| 08-01-04 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "capabilities"` | ❌ W0 | ⬜ pending |
| 08-01-05 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "search"` | ❌ W0 | ⬜ pending |
| 08-01-06 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "race_category"` | ❌ W0 | ⬜ pending |
| 08-01-07 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "county"` | ❌ W0 | ⬜ pending |
| 08-01-08 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/test_smoke.py -x -k "election_date"` | ❌ W0 | ⬜ pending |
| 08-01-09 | 01 | 1 | INTG-03 | e2e | `uv run pytest tests/e2e/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New election seed rows in `tests/e2e/conftest.py` (4-5 elections + 1 soft-deleted)
- [ ] New UUID constants exported from conftest for seeded elections
- [ ] Cleanup deletes for new election IDs in seed_database fixture
- [ ] Update existing count assertions to use `>=` if needed

*Existing pytest + pytest-asyncio infrastructure covers all framework needs.*

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
