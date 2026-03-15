---
phase: 01-data-contracts
plan: 03
subsystem: docs
tags: [pydantic-v2, jsonl, documentation, uuid, migration, backfill, county-reference]

# Dependency graph
requires:
  - phase: 01-data-contracts plan 01
    provides: Markdown format specs (multi-contest, single-contest, overview, county-reference) and vocabularies (seat-ids, boundary-types, election-types)
  - phase: 01-data-contracts plan 02
    provides: Four JSONL Pydantic models (ElectionEventJSONL, ElectionJSONL, CandidateJSONL, CandidacyJSONL) with model_json_schema() support
provides:
  - Auto-generated JSONL field documentation from Pydantic models (4 markdown files)
  - Generation script (tools/generate_jsonl_docs.py) for keeping docs in sync with code
  - Bibb county reference with complete Governing Bodies table (5 bodies, 12 contests)
  - UUID strategy spec (embedding format, validation rules, lifecycle)
  - Backfill rules spec (natural key definitions for ElectionEvent, Election, Candidate matching)
  - Migration rules spec (per-file-type deterministic transformation rules for ~200 legacy files)
  - data/candidates/ directory placeholder
affects: [02-converter, 02-importer, 02-migration-script, 02-backfill-command]

# Tech tracking
tech-stack:
  added: []
  patterns: [model_json_schema() doc generation pipeline, tools/ directory for standalone scripts]

key-files:
  created:
    - tools/generate_jsonl_docs.py
    - docs/formats/jsonl/election-events.md
    - docs/formats/jsonl/elections.md
    - docs/formats/jsonl/candidates.md
    - docs/formats/jsonl/candidacies.md
    - docs/formats/specs/uuid-strategy.md
    - docs/formats/specs/backfill-rules.md
    - docs/formats/specs/migration-rules.md
    - data/candidates/.gitkeep
  modified:
    - data/states/GA/counties/bibb.md
    - pyproject.toml

key-decisions:
  - "Doc generation uses model_json_schema() directly rather than manual field lists -- docs are always in sync with Pydantic models"
  - "UUID converter validates strictly: missing/invalid/duplicate UUIDs are always errors, never silently generated"
  - "Backfill order is ElectionEvents -> Elections -> Candidates due to foreign key dependencies"
  - "Migration creates candidate stubs with 00000000 placeholder in filename, replaced during backfill"
  - "County reference Body IDs use bibb-civil-magistrate (matching plan spec) rather than bibb-magistrate-court (from worked example in county-reference.md)"

patterns-established:
  - "tools/ directory for standalone scripts with T20 ruff ignore for print statements"
  - "Process spec documents define concrete error message formats for implementation"
  - "Governing Bodies table as the single mapping from Body ID to boundary_type"

requirements-completed: [FMT-01, FMT-02, FMT-03, FMT-04, FMT-05, FMT-06]

# Metrics
duration: 6min
completed: 2026-03-14
---

# Phase 1 Plan 3: JSONL Doc Generation, Bibb Example, and Process Specs Summary

**Auto-generated JSONL field docs from Pydantic models, complete Bibb governing bodies reference, and three Phase 2 process specs (UUID strategy, backfill rules, migration rules)**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-14T00:58:24Z
- **Completed:** 2026-03-14T01:04:30Z
- **Tasks:** 2
- **Files created/modified:** 11

## Accomplishments

- Created idempotent doc generation script that reads model_json_schema() and renders field tables with type, required/optional, default, and description for all 4 JSONL models
- Enhanced Bibb county reference with 5 governing bodies covering all 12 contests (BOE, civil/magistrate court, superior court, state court, water authority)
- Wrote UUID strategy spec with strict validation-error-on-missing rule and complete lifecycle documentation
- Wrote backfill rules spec defining natural key matching for all 3 entity types with conflict resolution and CLI interface
- Wrote migration rules spec with deterministic per-file-type transformations (overview, single-contest, multi-contest, special, candidate stubs) -- no judgment calls required

## Task Commits

Each task was committed atomically:

1. **Task 1: JSONL doc generation script and generate docs** - `a628be2` (feat)
2. **Task 2: Enhance Bibb county reference and create process specs** - `c54a734` (feat)

## Files Created/Modified

- `tools/generate_jsonl_docs.py` - Standalone script reading Pydantic model_json_schema() and rendering markdown field docs
- `docs/formats/jsonl/election-events.md` - Auto-generated ElectionEventJSONL field documentation (14 fields)
- `docs/formats/jsonl/elections.md` - Auto-generated ElectionJSONL field documentation (21 fields)
- `docs/formats/jsonl/candidates.md` - Auto-generated CandidateJSONL field documentation (10 fields + embedded CandidateLinkJSONL)
- `docs/formats/jsonl/candidacies.md` - Auto-generated CandidacyJSONL field documentation (12 fields)
- `data/states/GA/counties/bibb.md` - Enhanced with Governing Bodies table (5 bodies, all 12 Bibb contests mapped)
- `docs/formats/specs/uuid-strategy.md` - UUID embedding, validation rules, lifecycle, error message formats
- `docs/formats/specs/backfill-rules.md` - Natural key matching rules, conflict resolution, CLI spec
- `docs/formats/specs/migration-rules.md` - Per-file-type migration rules, Body/Seat inference tables, candidate stub creation
- `data/candidates/.gitkeep` - Empty directory placeholder for global candidate files
- `pyproject.toml` - Added T20 ruff per-file ignore for tools/ directory

## Decisions Made

- **Doc generation from schema:** Uses model_json_schema() directly so docs are always in sync with Pydantic models. No manual field lists to maintain.
- **Strict UUID validation:** Converter must emit validation errors on missing, invalid, or duplicate UUIDs. Never silently generates -- this prevents identity drift and ensures idempotency.
- **Ordered backfill:** ElectionEvents first, then Elections, then Candidates. Foreign key dependencies require this order. Missing dependencies emit error and skip.
- **Candidate stub naming:** `{name-slug}-00000000.md` with placeholder replaced during backfill. Ensures filenames are deterministic before UUIDs exist.
- **bibb-civil-magistrate Body ID:** Plan spec uses `bibb-civil-magistrate` for the Civil/Magistrate Court. The county-reference.md worked example used `bibb-magistrate-court`, but the plan spec takes precedence.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added T20 ruff per-file ignore for tools/ directory**
- **Found during:** Task 1
- **Issue:** ruff T201 rule flags print() in tools/generate_jsonl_docs.py, but print is the correct output mechanism for standalone CLI scripts
- **Fix:** Added `"tools/**/*.py" = ["T20"]` to pyproject.toml per-file-ignores
- **Files modified:** pyproject.toml
- **Verification:** `uv run ruff check tools/generate_jsonl_docs.py` passes
- **Committed in:** a628be2 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for lint compliance. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 (Data Contracts) is now complete: all 3 plans delivered
- Phase 2 implementers have unambiguous specs for: converter validation (UUID strategy), DB-to-markdown correlation (backfill rules), and legacy file migration (migration rules)
- JSONL docs are auto-generated and can be refreshed anytime the Pydantic models change
- Bibb county reference serves as the worked example for other county reference files
- data/candidates/ directory is ready for candidate stub creation during migration

## Self-Check: PASSED

- All 11 created/modified files verified on disk
- Both task commits (a628be2, c54a734) verified in git log

---
*Phase: 01-data-contracts*
*Completed: 2026-03-14*
