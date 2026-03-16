---
phase: 6
slug: capabilities-discovery
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-16
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/unit/ tests/integration/ -x -q` |
| **Full suite command** | `uv run pytest --cov=voter_api --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ tests/integration/ -x -q`
- **After every plan wave:** Run `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | DISC-01 | unit | `uv run pytest tests/unit/schemas/test_election_capabilities.py -v` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | DISC-01, INTG-01 | integration | `uv run pytest tests/integration/test_api/test_elections_capabilities.py -v` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | INTG-01 | integration | `uv run pytest tests/integration/test_api/test_elections_capabilities.py -k "route_ordering" -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

- pytest, httpx, and test helpers (`make_test_app`) already exist
- No new test dependencies needed

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
