---
phase: 03-claude-code-skills
plan: 01
subsystem: lib
tags: [normalizer, title-case, text-normalization, tdd, pure-functions]

# Dependency graph
requires: []
provides:
  - "lib/normalizer/ package with smart_title_case, normalize_url, normalize_date, normalize_occupation"
  - "NormalizationReport class for terminal and JSON reporting"
  - "NormalizationResult, FileChange, FileNormalizationResult dataclasses"
  - "65 passing unit tests covering all edge cases"
affects: [03-02, 03-03, 03-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure function normalization rules with no side effects or file I/O"
    - "TDD: failing tests committed before implementation"
    - "Idempotent functions: applying twice gives same result"
    - "Occupation mode flag to vary behavior without separate functions"
    - "Placeholder passthrough: --, em-dash return unchanged"
    - "Report class pattern matching lib/converter/report.py structure"

key-files:
  created:
    - src/voter_api/lib/normalizer/__init__.py
    - src/voter_api/lib/normalizer/types.py
    - src/voter_api/lib/normalizer/title_case.py
    - src/voter_api/lib/normalizer/rules.py
    - src/voter_api/lib/normalizer/report.py
    - tests/unit/lib/test_normalizer/__init__.py
    - tests/unit/lib/test_normalizer/test_title_case.py
    - tests/unit/lib/test_normalizer/test_rules.py
    - tests/unit/lib/test_normalizer/test_report.py
  modified: []

key-decisions:
  - "Mac prefix detection requires >4 char word to avoid matching common words like MACHINIST"
  - "Mc prefix detection requires >2 chars (shorter names always safe to apply)"
  - "Single-letter middle initial check runs before lowercase article check to avoid 'A' being lowercased"
  - "Occupation acronyms only applied in is_occupation=True mode to avoid false positives in name mode"
  - "report.py created during Task 1 (not Task 2) to unblock __init__.py import -- tests added in Task 2"

patterns-established:
  - "UPPERCASE_SUFFIXES frozenset for generational suffixes (III, II, IV) -- stay fully uppercase"
  - "TITLE_SUFFIXES frozenset for Jr/Sr -- title-cased (Jr not JR)"
  - "LOWERCASE_WORDS frozenset for articles/prepositions in name mode"
  - "OCCUPATION_ACRONYMS frozenset for known professional designations"
  - "OCCUPATION_LOWERCASE frozenset (narrower than LOWERCASE_WORDS) for occupation context"

requirements-completed: [SKL-02]

# Metrics
duration: 5min
completed: 2026-03-15
---

# Phase 3 Plan 01: Normalizer Library Core Summary

**Pure-function normalizer library with smart title case (SOS edge cases), URL/date/occupation rules, and NormalizationReport -- 65 tests passing via TDD**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-15T04:43:40Z
- **Completed:** 2026-03-15T04:48:45Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- `smart_title_case` handles ALL CAPS SOS names: Mc/Mac/O' prefixes, generational suffixes (Jr, Sr, III, II, IV), hyphenated names, lowercase articles, single-letter middle initials with periods, and occupation mode with acronym preservation
- Three pure normalization rules: `normalize_url` (https upgrade, lowercase, placeholder passthrough), `normalize_date` (slash/ISO format conversion, zero-padding), `normalize_occupation` (title case via occupation mode)
- `NormalizationReport` class follows `converter/report.py` pattern: tracks successes/failures/warnings/UUID generation/file renames, renders terminal table and writes JSON report
- 65 unit tests across three test files covering all parametrized edge cases

## Task Commits

Each task was committed atomically:

1. **Task 1: Smart title case and individual normalization rules (TDD)**
   - RED: `a383369` (test: add failing tests)
   - GREEN+REFACTOR: `3cc6812` (feat: implement normalizer library core)

2. **Task 2: Report generator following converter pattern (TDD)**
   - GREEN+tests: `190f341` (feat: add NormalizationReport tests and complete task 2)

_Note: report.py was implemented during Task 1 to unblock the package __init__.py import; tests were added in Task 2._

## Files Created/Modified

- `src/voter_api/lib/normalizer/__init__.py` - Public API: normalize_directory, normalize_file stubs + NormalizationReport, smart_title_case exports
- `src/voter_api/lib/normalizer/types.py` - NormalizationResult, FileChange, FileNormalizationResult dataclasses
- `src/voter_api/lib/normalizer/title_case.py` - smart_title_case with UPPERCASE_SUFFIXES, TITLE_SUFFIXES, LOWERCASE_WORDS, OCCUPATION_ACRONYMS frozensets
- `src/voter_api/lib/normalizer/rules.py` - normalize_url, normalize_date, normalize_occupation pure functions
- `src/voter_api/lib/normalizer/report.py` - NormalizationReport class with FileResult dataclass
- `tests/unit/lib/test_normalizer/test_title_case.py` - 23 tests (parametrized) for smart_title_case
- `tests/unit/lib/test_normalizer/test_rules.py` - 25 tests for URL/date/occupation rules
- `tests/unit/lib/test_normalizer/test_report.py` - 17 tests for NormalizationReport

## Decisions Made

- Mac prefix detection requires word length > 4 (not > 3) to avoid false positives: "MACHINIST" starts with "MAC" but has 9 chars and the remainder "HINIST" incorrectly triggered Mac-prefix -- raised min length to guard against common English words starting with MAC/MACH
- Single-letter middle initial check runs before lowercase article check: "A" is both a single letter AND a lowercase article; initial check must win to produce "A." not "a"
- `report.py` implemented during Task 1 to unblock `__init__.py` import chain; Task 2 added tests against the already-working implementation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Mac prefix length guard raised from 4 to 5 to prevent MACHINIST -> MacHinist**
- **Found during:** Task 1 (GREEN phase, first test run)
- **Issue:** `_apply_mc_mac_prefix("MACHINIST")` returned "MacHinist" because "MACHINIST".upper() starts with "MAC" and the 4-char condition `len(word) > 3` was met (9 > 3)
- **Fix:** Changed condition to `len(word) > 4` in `_title_word` and added `is_occupation` guard (Mac prefix only in name mode)
- **Files modified:** src/voter_api/lib/normalizer/title_case.py
- **Verification:** `uv run pytest tests/unit/lib/test_normalizer/test_title_case.py -x -v` -- all 23 tests pass
- **Committed in:** 3cc6812 (Task 1 feat commit)

**2. [Rule 3 - Blocking] report.py created during Task 1 to unblock __init__.py import**
- **Found during:** Task 1 (GREEN phase, first import attempt)
- **Issue:** `__init__.py` imports `NormalizationReport` from `report.py` which didn't exist yet; import failure blocked all Task 1 tests
- **Fix:** Implemented `report.py` fully (Task 2's implementation) during Task 1 to unblock the package import
- **Files modified:** src/voter_api/lib/normalizer/report.py
- **Verification:** Tests imported and ran successfully after creation
- **Committed in:** 3cc6812 (Task 1 feat commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both auto-fixes necessary for correctness and task completion. No scope creep. Task 2 tests still written against the report.py implementation as designed.

## Issues Encountered

None beyond the two auto-fixed deviations above.

## Next Phase Readiness

- `lib/normalizer/` package is fully importable and tested
- `normalize_directory` and `normalize_file` are stubbed with `NotImplementedError` -- ready for Plan 03-02 implementation
- All normalization rules are pure functions: safe to call from any context
- `NormalizationReport` ready to use as the output type for directory/file normalization operations

---
*Phase: 03-claude-code-skills*
*Completed: 2026-03-15*
