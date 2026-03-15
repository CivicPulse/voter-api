---
phase: 2
slug: converter-and-import-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-15
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
| 02-01-01 | 01 | 1 | IMP-01 | integration | `uv run pytest tests/integration/test_election_event_import.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | IMP-02 | integration | `uv run pytest tests/integration/test_candidate_import.py -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | CNV-01 | unit | `uv run pytest tests/unit/lib/test_converter/test_parser.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | CNV-02 | unit | `uv run pytest tests/unit/lib/test_converter/test_writer.py -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | CNV-03 | unit + integration | `uv run pytest tests/unit/lib/test_converter/test_directory.py -x` | ❌ W0 | ⬜ pending |
| 02-02-04 | 02 | 1 | CNV-04 | unit | `uv run pytest tests/unit/lib/test_converter/test_report.py -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | IMP-01 | integration | `uv run pytest tests/integration/test_election_import.py -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | IMP-03 | integration | `uv run pytest tests/integration/ -k "idempotent" -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | IMP-04 | integration | `uv run pytest tests/integration/ -k "dry_run" -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/lib/test_converter/` — entire test directory for new converter library
- [ ] `tests/unit/lib/test_converter/test_parser.py` — covers CNV-01 (mistune AST parsing)
- [ ] `tests/unit/lib/test_converter/test_writer.py` — covers CNV-02 (Pydantic validation)
- [ ] `tests/unit/lib/test_converter/test_resolver.py` — covers Body/Seat resolution
- [ ] `tests/unit/lib/test_converter/test_directory.py` — covers CNV-03 (batch processing)
- [ ] `tests/unit/lib/test_converter/test_report.py` — covers CNV-04 (validation report)
- [ ] `tests/integration/test_election_event_import.py` — covers IMP-01 (election event import)
- [ ] `tests/integration/test_election_import.py` — covers IMP-01 (election import)
- [ ] `tests/integration/test_candidacy_import.py` — covers IMP-02 (candidacy import)
- [ ] Framework install: `uv add mistune` — mistune not yet in dependencies
- [ ] E2E tests need seed data updates for new candidacy model after migration

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| County reference file completeness | CNV-01 | 159 files, content quality verification | Spot-check 5 random county files for governing body accuracy |
| Existing file migration | CNV-03 | ~200 files, format correctness | Run `convert migrate-format` on test subset, diff results |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
