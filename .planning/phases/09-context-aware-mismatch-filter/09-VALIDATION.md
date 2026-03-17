---
phase: 9
slug: context-aware-mismatch-filter
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-16
audited: 2026-03-16
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
| **Estimated runtime** | ~3 seconds (phase-relevant tests) |

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
| 09-01-01 | 01 | 1 | MISMATCH-01 | unit | `uv run pytest tests/unit/test_services/test_voter_history_service.py -x -q -k "build_mismatch_filter"` | ✅ | ✅ green |
| 09-01-02 | 01 | 1 | MISMATCH-01 | unit | `uv run pytest tests/unit/test_services/test_voter_history_service.py -x -q -k "mismatch_filter_error"` | ✅ | ✅ green |
| 09-01-03 | 01 | 1 | MISMATCH-01 | integration | `uv run pytest tests/integration/test_voter_history_api.py -x -q -k "mismatch"` | ✅ | ✅ green |
| 09-02-01 | 02 | 2 | MISMATCH-01 | unit+integration | `uv run pytest tests/unit/test_services/test_voter_history_service.py tests/integration/test_voter_history_api.py -x -k "mismatch"` | ✅ | ✅ green |
| 09-02-02 | 02 | 2 | MISMATCH-01 | e2e | `uv run pytest tests/e2e/ --collect-only` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement Coverage Detail

### MISMATCH-01: Context-Aware District Mismatch Filter

| Truth / Behavior | Test File | Test Name(s) | Level |
|-----------------|-----------|---------------|-------|
| `has_district_mismatch=true` scoped to election district_type | `test_voter_history_service.py` | `test_build_mismatch_filter_true_returns_clause_element`, `test_mismatch_filter_true_returns_district_type` | unit |
| `has_district_mismatch=false` excludes mismatched+unanalyzed | `test_voter_history_service.py` | `test_build_mismatch_filter_false_returns_clause_element`, `test_mismatch_filter_false_returns_district_type` | unit |
| Omitting filter returns all (no analysis JOIN) | `test_voter_history_service.py` | `test_mismatch_filter_omitted_returns_none_district_type` | unit |
| Null district_type → MismatchFilterError / 422 | `test_voter_history_service.py`, `test_voter_history_api.py` | `test_mismatch_filter_error_null_district_type`, `test_participation_mismatch_null_district_type_422` | unit+integration |
| Unknown district_type → MismatchFilterError / 422 | `test_voter_history_service.py`, `test_voter_history_api.py` | `test_mismatch_filter_error_unknown_district_type`, `test_participation_mismatch_unknown_district_type_422` | unit+integration |
| false filter also errors on null district_type | `test_voter_history_service.py`, `test_voter_history_api.py` | `test_mismatch_filter_false_also_errors_on_null_district_type`, `test_participation_mismatch_false_422_null_district_type` | unit+integration |
| `mismatch_count` in stats response | `test_voter_history_api.py` | `test_participation_stats_mismatch_count`, `test_participation_stats_mismatch_count_null_when_no_district` | integration |
| `mismatch_district_type` in participation response | `test_voter_history_api.py` | `test_participation_mismatch_district_type_in_response`, `test_participation_no_mismatch_filter_null_district_type_field` | integration |
| `_build_mismatch_filter` true/false produce different clauses | `test_voter_history_service.py` | `test_build_mismatch_filter_true_and_false_are_different`, `test_build_mismatch_filter_different_types` | unit |
| E2E: 422 on no district_type | `test_smoke.py` | `test_participation_mismatch_filter_422_no_district_type` | e2e |
| E2E: returns district_type in response | `test_smoke.py` | `test_participation_mismatch_filter_returns_district_type` | e2e |
| E2E: mismatch_count in stats | `test_smoke.py` | `test_participation_stats_has_mismatch_count` | e2e |

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-election mismatch isolation | MISMATCH-01 | Requires real PostGIS + multiple elections with different district_types | Run E2E suite with seeded elections of varying district_types |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-03-16

---

## Validation Audit 2026-03-16

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

**Test counts:** 12 unit tests, 7 integration tests, 3 E2E smoke tests (22 total mismatch-specific tests)
**Suite result:** 90 passed, 0 failed (voter history service + API files)
