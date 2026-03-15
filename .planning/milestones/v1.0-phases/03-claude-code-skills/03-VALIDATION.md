---
phase: 3
slug: claude-code-skills
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-15
validated: 2026-03-15
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + Hypothesis 6.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/lib/test_normalizer/ -x` |
| **Full suite command** | `uv run pytest --cov=voter_api --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/lib/test_normalizer/ -x && uv run ruff check . && uv run ruff format --check .`
- **After every plan wave:** Run `uv run pytest --cov=voter_api --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green + normalizer produces clean output on all three election CSVs
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | SKL-02 | unit | `uv run pytest tests/unit/lib/test_normalizer/test_title_case.py -x` | [x] | ✅ green |
| 03-01-02 | 01 | 1 | SKL-02 | unit | `uv run pytest tests/unit/lib/test_normalizer/test_rules.py -x` | [x] | ✅ green |
| 03-01-03 | 01 | 1 | SKL-02 | unit (golden) | `uv run pytest tests/unit/lib/test_normalizer/test_golden_files.py -x` | [x] | ✅ green |
| 03-01-04 | 01 | 1 | SKL-02 | unit (property) | `uv run pytest tests/unit/lib/test_normalizer/test_idempotency.py -x` | [x] | ✅ green |
| 03-01-05 | 01 | 1 | SKL-02 | integration | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | [x] | ✅ green |
| 03-02-01 | 02 | 2 | SKL-01 | integration (pipeline) | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | [x] | ✅ green |
| 03-02-02 | 02 | 2 | SKL-03 | integration (pipeline) | `uv run voter-api normalize elections data/elections/2026-05-19/ --dry-run` | [x] | ✅ green |
| 03-02-03 | 02 | 2 | SKL-04 | manual | Inspect enriched candidate files, run normalizer | N/A | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/lib/test_normalizer/__init__.py` — package init
- [x] `tests/unit/lib/test_normalizer/test_title_case.py` — smart title case rules
- [x] `tests/unit/lib/test_normalizer/test_rules.py` — URL, date, occupation rules
- [x] `tests/unit/lib/test_normalizer/test_golden_files.py` — before/after fixtures
- [x] `tests/unit/lib/test_normalizer/test_idempotency.py` — Hypothesis property tests
- [x] `tests/fixtures/normalizer/` — golden file fixtures directory
- [x] `tests/fixtures/normalizer/synthetic.csv` — synthetic SOS CSV fixture
- [x] Hypothesis dev dependency: `uv add --dev hypothesis`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Qualified-candidates skill produces valid markdown from SOS CSV | SKL-01 | AI skill output varies per invocation; validated by downstream normalizer pass | Run skill on CSV, then `uv run voter-api normalize elections <dir> --dry-run` — no structural errors |
| Election-calendar skill extracts correct dates from PDF | SKL-03 | AI reads PDF natively; output validated by normalizer | Run skill on PDF, inspect metadata fields in output, run normalizer |
| Enrichment skill adds valid candidate data | SKL-04 | AI web research output varies; validated by normalizer + human review | Run skill, inspect candidate files for enriched fields, run normalizer |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (2026-03-15)
