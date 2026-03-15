---
phase: 02-converter-and-import-pipeline
plan: 02
subsystem: converter
tags: [mistune, markdown, jsonl, pydantic, cli, typer, boundary-types]

# Dependency graph
requires:
  - phase: 01-data-contracts
    provides: JSONL Pydantic schemas, markdown format specs, vocabularies, county reference format
provides:
  - lib/converter/ library with parser, writer, resolver, report modules
  - convert_directory() and convert_file() public API
  - voter-api convert CLI command (directory + file subcommands)
  - 159 county reference files with Governing Bodies tables
  - Body ID to boundary_type resolution for all GA counties
affects: [02-03-import-pipeline, 03-skills]

# Tech tracking
tech-stack:
  added: [mistune 3.2.0]
  patterns: [mistune AST parsing, deterministic markdown-to-JSONL conversion, county reference file lookup]

key-files:
  created:
    - src/voter_api/lib/converter/__init__.py
    - src/voter_api/lib/converter/parser.py
    - src/voter_api/lib/converter/writer.py
    - src/voter_api/lib/converter/resolver.py
    - src/voter_api/lib/converter/report.py
    - src/voter_api/lib/converter/types.py
    - src/voter_api/cli/convert_cmd.py
    - tests/unit/lib/test_converter/test_parser.py
    - tests/unit/lib/test_converter/test_writer.py
    - tests/unit/lib/test_converter/test_resolver.py
    - tests/unit/lib/test_converter/test_report.py
    - tests/unit/lib/test_converter/test_directory.py
  modified:
    - src/voter_api/cli/app.py
    - data/states/GA/counties/*.md (158 files populated)
    - pyproject.toml
    - uv.lock

key-decisions:
  - "mistune AST mode (renderer=None) for deterministic token-based parsing -- no HTML rendering needed"
  - "Pydantic model_validate at conversion time (not just write time) to catch errors early"
  - "election_event_id placeholder UUID during conversion -- resolved during import phase"
  - "Standard 9-body governing bodies template for county reference files (BOE, BOC, courts, sheriff, etc.)"
  - "mistune table plugin: table_head children are direct table_cell tokens (no table_row wrapper)"

patterns-established:
  - "Converter library pattern: lib/converter/ with parser, writer, resolver, report, types submodules"
  - "County reference file format: Governing Bodies table with Body Name, Body ID, Boundary Type, Election Type, Seats columns"
  - "Body ID resolution chain: statewide built-in mapping checked first, then county reference lookup"

requirements-completed: [CNV-01, CNV-02, CNV-03, CNV-04]

# Metrics
duration: 16min
completed: 2026-03-15
---

# Phase 02 Plan 02: Converter Library Summary

**Deterministic markdown-to-JSONL converter using mistune AST parsing with Pydantic validation, county reference resolution for all 159 GA counties, and voter-api convert CLI**

## Performance

- **Duration:** 16 min
- **Started:** 2026-03-15T01:34:56Z
- **Completed:** 2026-03-15T01:51:34Z
- **Tasks:** 2
- **Files modified:** 188

## Accomplishments
- Built complete lib/converter/ library parsing all three markdown file types (overview, single-contest, multi-contest)
- Parser extracts metadata tables, candidate tables, calendar data, and Body/Seat metadata lines via mistune AST
- Writer validates records against JSONL Pydantic schemas (ElectionEventJSONL, ElectionJSONL) before writing
- Resolver maps Body IDs to boundary_type using statewide built-in mapping (16 entries) and county reference file lookup
- Populated all 159 county reference files with standard Governing Bodies tables
- Added voter-api convert directory/file CLI commands
- 50 unit tests covering parser, writer, resolver, report, and directory conversion

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing converter tests** - `aa3b9c2` (test)
2. **Task 1 (GREEN): Implement converter library** - `d2df213` (feat)
3. **Task 2: CLI command and county reference population** - `c36c90b` (feat)

_TDD task had RED/GREEN commits. No refactor phase needed._

## Files Created/Modified
- `src/voter_api/lib/converter/__init__.py` - Public API: convert_directory(), convert_file()
- `src/voter_api/lib/converter/parser.py` - mistune AST parsing for all three file types
- `src/voter_api/lib/converter/writer.py` - JSONL record generation with Pydantic validation
- `src/voter_api/lib/converter/resolver.py` - Body ID to boundary_type resolution (STATEWIDE_BODIES + county lookup)
- `src/voter_api/lib/converter/report.py` - ConversionReport with terminal and JSON output
- `src/voter_api/lib/converter/types.py` - ParseResult, ContestData, ConversionResult, FileType
- `src/voter_api/cli/convert_cmd.py` - voter-api convert directory/file CLI commands
- `src/voter_api/cli/app.py` - Registered convert subcommand
- `data/states/GA/counties/*.md` - 158 files populated with Governing Bodies tables (Bibb unchanged)
- `tests/unit/lib/test_converter/` - 5 test files, 50 tests total

## Decisions Made
- Used mistune's AST mode (renderer=None) instead of HTML rendering -- tokens provide structured access to metadata tables and heading hierarchy
- Discovered mistune table plugin puts table_head cells as direct children (no table_row wrapper) while table_body rows do have table_row wrappers -- fixed parser to handle this AST quirk
- Added Pydantic model_validate in parse_result_to_records (not just write_jsonl) so validation errors are caught at conversion time
- election_event_id uses placeholder UUID (00000000...) during conversion since resolving it requires reading the referenced overview file -- import pipeline (Plan 02-03) will handle this resolution
- County reference files use a standard 9-body template as conservative defaults -- accurate per-county customization deferred to Phase 3 skills work

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed mistune table_head AST structure assumption**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Parser assumed table_head -> table_row -> table_cell structure, but mistune AST uses table_head -> table_cell (direct children, no row wrapper)
- **Fix:** Updated _parse_candidate_table to iterate table_head children directly for cell extraction
- **Files modified:** src/voter_api/lib/converter/parser.py
- **Verification:** All 50 tests pass including candidate table parsing
- **Committed in:** d2df213 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential fix for correct table parsing. No scope creep.

## Issues Encountered
None beyond the mistune AST structure issue (documented as deviation above).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Converter library ready for integration with import pipeline (Plan 02-03)
- All 159 county reference files have governing bodies for resolver
- JSONL output validates against Phase 1 Pydantic schemas
- CLI commands registered and functional
- County reference files may need per-county customization in Phase 3 (seat counts, state court presence, etc.)

---
*Phase: 02-converter-and-import-pipeline*
*Completed: 2026-03-15*
