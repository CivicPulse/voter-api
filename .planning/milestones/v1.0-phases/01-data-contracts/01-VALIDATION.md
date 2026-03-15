---
phase: 1
slug: data-contracts
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-14
validated: 2026-03-15
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
| **Estimated runtime** | ~0.4 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py -x`
- **After every plan wave:** Run `uv run pytest tests/unit/test_schemas/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** <1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-02-T1 | 01-02 | 1 | FMT-04 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::TestElectionEventJSONL::test_valid_record tests/unit/test_schemas/test_jsonl_schemas.py::TestElectionJSONL::test_valid_record -x` | ✅ | ✅ green |
| 01-02-T1 | 01-02 | 1 | FMT-05 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::TestCandidateJSONL::test_valid_person_record tests/unit/test_schemas/test_jsonl_schemas.py::TestCandidacyJSONL::test_valid_junction_record -x` | ✅ | ✅ green |
| 01-02-T1 | 01-02 | 1 | FMT-06 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::TestSchemaVersionConsistency -x` | ✅ | ✅ green |
| 01-02-T1 | 01-02 | 1 | FMT-04 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::TestElectionJSONL::test_invalid_election_type_rejected tests/unit/test_schemas/test_jsonl_schemas.py::TestElectionEventJSONL::test_invalid_event_type_rejected -x` | ✅ | ✅ green |
| 01-02-T1 | 01-02 | 1 | FMT-05 | unit | `uv run pytest tests/unit/test_schemas/test_jsonl_schemas.py::TestCandidacyJSONL::test_invalid_filing_status_rejected -x` | ✅ | ✅ green |
| 01-01-T1/T2 | 01-01 | 1 | FMT-01, FMT-02, FMT-03 | manual | N/A | N/A | ✅ reviewed |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_schemas/test_jsonl_schemas.py` — 68 tests covering all 4 JSONL models, enums, and CandidateLinkJSONL
- [x] `src/voter_api/schemas/jsonl/__init__.py` — package exists with all exports

*Wave 0 stubs were created and fully implemented during plan 01-02 execution.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Markdown format specs correctly represent any Georgia contest with district linkage | FMT-01 | Prose specification validated by human review | Review spec docs; verify Bibb County example covers all contest types |
| Markdown format specs include election metadata fields | FMT-02 | Prose specification validated by human review | Review spec docs; verify all calendar date fields are documented |
| Markdown format specs include candidate detail fields | FMT-03 | Prose specification validated by human review | Review spec docs; verify candidate file format has all enrichment fields |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 1s (0.39s actual)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated (2026-03-15)

---

## Validation Audit 2026-03-15

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Tests passing | 68 |
| Manual-only | 3 (FMT-01, FMT-02, FMT-03) |
