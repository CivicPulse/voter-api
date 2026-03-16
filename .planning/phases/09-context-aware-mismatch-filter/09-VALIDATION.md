---
phase: 9
slug: context-aware-mismatch-filter
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest --cov=voter_api --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | MISMATCH-01 | unit | `uv run pytest tests/unit/services/test_voter_history_service.py -x -q` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | MISMATCH-01 | unit | `uv run pytest tests/unit/schemas/test_voter_history.py -x -q` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | MISMATCH-01 | integration | `uv run pytest tests/integration/api/test_voter_history.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/services/test_voter_history_mismatch.py` — stubs for MISMATCH-01 context-aware filter logic
- [ ] `tests/integration/api/test_participation_mismatch.py` — integration test stubs for participation endpoint mismatch filtering

*Existing infrastructure covers framework and fixture needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-election mismatch isolation | MISMATCH-01 | Requires real PostGIS + multiple elections with different district_types | Run E2E suite with seeded elections of varying district_types |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
