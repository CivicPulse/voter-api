---
phase: 2
slug: converter-and-import-pipeline
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-15
audited: 2026-03-15
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/lib/test_converter/ -x` |
| **Full suite command** | `uv run pytest --cov=voter_api --cov-report=term-missing` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/lib/test_converter/ -x` (converter tasks) or `uv run pytest tests/integration/ -k "import" -x` (import tasks)
- **After every plan wave:** Run `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite + E2E must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | IMP-01 | integration | `uv run pytest tests/integration/test_election_event_import.py -x` | ✅ | ✅ green |
| 02-01-02 | 01 | 1 | IMP-02 | integration | `uv run pytest tests/integration/test_candidate_import_service.py -x` | ✅ | ✅ green |
| 02-02-01 | 02 | 1 | CNV-01 | unit | `uv run pytest tests/unit/lib/test_converter/test_parser.py -x` | ✅ | ✅ green |
| 02-02-02 | 02 | 1 | CNV-02 | unit | `uv run pytest tests/unit/lib/test_converter/test_writer.py -x` | ✅ | ✅ green |
| 02-02-03 | 02 | 1 | CNV-03 | unit + integration | `uv run pytest tests/unit/lib/test_converter/test_directory.py -x` | ✅ | ✅ green |
| 02-02-04 | 02 | 1 | CNV-04 | unit | `uv run pytest tests/unit/lib/test_converter/test_report.py -x` | ✅ | ✅ green |
| 02-03-01 | 03 | 2 | IMP-01 | integration | `uv run pytest tests/integration/test_election_event_import.py::TestImportElections -x` | ✅ | ✅ green |
| 02-03-02 | 03 | 2 | IMP-03 | integration | `uv run pytest tests/integration/test_election_event_import.py -k "reimport" -x` | ✅ | ✅ green |
| 02-03-03 | 03 | 2 | IMP-04 | integration | `uv run pytest tests/integration/test_election_event_import.py -k "dry_run" -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/lib/test_converter/` — 50 tests across 5 test files
- [x] `tests/unit/lib/test_converter/test_parser.py` — 15 tests, covers CNV-01 (mistune AST parsing)
- [x] `tests/unit/lib/test_converter/test_writer.py` — 7 tests, covers CNV-02 (Pydantic validation)
- [x] `tests/unit/lib/test_converter/test_resolver.py` — 14 tests, covers Body/Seat resolution
- [x] `tests/unit/lib/test_converter/test_directory.py` — 7 tests, covers CNV-03 (batch processing)
- [x] `tests/unit/lib/test_converter/test_report.py` — 7 tests, covers CNV-04 (validation report)
- [x] `tests/integration/test_election_event_import.py` — 13 tests, covers IMP-01, IMP-03, IMP-04 (election event + election + candidacy imports, idempotency, dry-run)
- [x] `tests/integration/test_candidate_import_service.py` — 9 tests, covers IMP-02 (candidate import + reimport)
- [x] Framework install: `uv add mistune` — mistune 3.2.0 installed
- [x] E2E tests updated with candidacy seed data (CANDIDACY_ID in conftest.py)
- Note: `test_election_import.py` and `test_candidacy_import.py` were not created as separate files; election and candidacy import tests are bundled in `test_election_event_import.py` (TestImportElections, TestImportCandidacies classes)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| County reference file completeness | CNV-01 | 159 files, content quality verification | Spot-check 5 random county files for governing body accuracy |
| Existing file migration | CNV-03 | ~200 files, format correctness | Run `convert migrate-format` on test subset, diff results |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete

---

## Validation Audit 2026-03-15

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |

**Details:**
- **IMP-03 (Idempotent reimport)**: Added 3 reimport tests (election_event, election, candidacy) to `test_election_event_import.py`
- **IMP-04 (Dry-run)**: Added 3 dry-run tests (election, candidacy, candidate-jsonl) to `test_election_event_import.py`
- Total test count: 50 unit + 22 integration = 72 automated tests covering all 9 requirements
