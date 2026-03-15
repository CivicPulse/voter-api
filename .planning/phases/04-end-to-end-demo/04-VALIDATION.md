---
phase: 4
slug: end-to-end-demo
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) |
| **Quick run command** | `uv run pytest tests/unit/lib/test_converter/ -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run ruff check . && uv run ruff format --check .`
- **After every plan wave:** Run `uv run pytest tests/unit/lib/test_converter/ tests/integration/test_election_event_import.py -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | DEM-01 | manual | Walkthrough execution (format migration + normalize) | N/A | ⬜ pending |
| 04-01-02 | 01 | 1 | DEM-01 | manual | Walkthrough execution (convert + import + query) | N/A | ⬜ pending |
| 04-01-03 | 01 | 1 | DEM-01 | manual | Walkthrough execution (documentation at `docs/pipeline-walkthrough.md`) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. DEM-01 is a documentation/demonstration requirement, not a code requirement. The underlying components (converter, import, API) are already tested:

- `tests/unit/lib/test_converter/` — Converter produces valid JSONL from enhanced-format MD
- `tests/integration/test_election_event_import.py` — Import service loads JSONL into DB
- `tests/e2e/test_smoke.py::TestElections` — API returns imported elections

No new test stubs needed for Wave 0.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full pipeline execution (SOS CSV → MD → JSONL → DB → API) | DEM-01 | Integration across all stages requires real data, real PostGIS, and human review of terminal output | Follow `docs/pipeline-walkthrough.md` end-to-end |
| Walkthrough is reproducible by another user | DEM-01 | Requires a human following documented steps | New developer follows walkthrough from scratch |
| Terminal output matches walkthrough code blocks | DEM-01 | Real output validation | Compare actual terminal output against documented expectations |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
