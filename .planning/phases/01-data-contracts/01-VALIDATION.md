---
phase: 1
slug: data-contracts
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py -x` |
| **Full suite command** | `uv run pytest tests/unit/test_schemas/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py -x`
- **After every plan wave:** Run `uv run pytest tests/unit/test_schemas/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 1 | FMT-04 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_election_jsonl_valid -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | FMT-05 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_candidate_and_candidacy_jsonl -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | FMT-06 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_schema_version_present -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | FMT-04 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_election_type_validation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | FMT-05 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::test_candidacy_filing_status_validation -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1 | FMT-01, FMT-02, FMT-03 | manual | N/A | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_schemas/test_jsonl_schemas.py` — stubs for FMT-04, FMT-05, FMT-06
- [ ] `src/voter_api/schemas/jsonl/__init__.py` — new package, doesn't exist yet

*Wave 0 creates the test stubs and package structure before implementation begins.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Markdown format specs correctly represent any Georgia contest with district linkage | FMT-01 | Prose specification validated by human review | Review spec docs; verify Bibb County example covers all contest types |
| Markdown format specs include election metadata fields | FMT-02 | Prose specification validated by human review | Review spec docs; verify all calendar date fields are documented |
| Markdown format specs include candidate detail fields | FMT-03 | Prose specification validated by human review | Review spec docs; verify candidate file format has all enrichment fields |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
