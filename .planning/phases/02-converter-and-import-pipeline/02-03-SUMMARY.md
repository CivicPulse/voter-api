---
phase: 02-converter-and-import-pipeline
plan: 03
subsystem: import, cli
tags: [jsonl, upsert, postgresql, typer, pydantic, migration, uuid-backfill]

# Dependency graph
requires:
  - phase: 01-data-contracts
    provides: JSONL Pydantic schemas for validation (ElectionEventJSONL, ElectionJSONL, CandidateJSONL, CandidacyJSONL)
  - phase: 02-converter-and-import-pipeline
    plan: 01
    provides: Candidacy ORM model, enhanced ElectionEvent model, Election with election_stage
  - phase: 02-converter-and-import-pipeline
    plan: 02
    provides: Converter library (markdown-to-JSONL), county reference files, convert CLI
provides:
  - Four JSONL import services (election_event, election, candidacy, candidate person-entity)
  - Shared jsonl_reader utility with per-line Pydantic validation
  - Five CLI import commands (4 individual + 1 pipeline in FK order)
  - File migration script (migrate-format) implementing migration-rules.md spec
  - UUID backfill command (backfill-uuids) implementing backfill-rules.md spec
  - All imports idempotent via UPSERT on UUID PK
  - Dry-run mode on all import and migration commands
affects: [03-skills]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "JSONL reader pattern: read_jsonl(path, PydanticModel) -> (valid, errors)"
    - "JSONL import service pattern: import_X(session, records, dry_run) -> summary dict"
    - "Pipeline command pattern: sequential imports in FK dependency order, stop on failure"
    - "File migration pattern: detect type -> transform in-place -> idempotency via Format Version check"

key-files:
  created:
    - src/voter_api/services/jsonl_reader.py
    - src/voter_api/services/election_event_import_service.py
    - src/voter_api/services/election_import_service.py
    - src/voter_api/services/candidacy_import_service.py
    - tests/integration/test_election_event_import.py
  modified:
    - src/voter_api/services/candidate_import_service.py
    - src/voter_api/cli/import_cmd.py
    - src/voter_api/cli/convert_cmd.py
    - tests/e2e/test_smoke.py

key-decisions:
  - "Separate candidates-jsonl command for person-entity model (vs updating existing candidates command)"
  - "Pipeline command (election-data) uses individual sessions per file type for isolation"
  - "UUID backfill uses direct DB queries in async session (not the import services)"
  - "Migration idempotency via Format Version row detection"
  - "COALESCE pattern for nullable fields in candidacy import preserves richer existing data"

patterns-established:
  - "JSONL import service: async function taking (session, records, dry_run) returning summary dict"
  - "read_jsonl utility: validates each line against Pydantic model, returns (valid, errors) tuple"
  - "CLI pipeline: sequential imports with stop-on-failure and summary reporting"

requirements-completed: [IMP-01, IMP-02, IMP-03, IMP-04, CNV-03]

# Metrics
duration: 11min
completed: 2026-03-15
---

# Phase 02 Plan 03: Import Pipeline and File Migration Summary

**Four JSONL-to-database import services with UPSERT idempotency, pipeline CLI command in FK order, file migration script, and UUID backfill command**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-15T01:55:14Z
- **Completed:** 2026-03-15T02:06:23Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Built shared jsonl_reader.py with per-line Pydantic validation against JSONL schemas
- Created three new import services (election_event, election, candidacy) following the existing UPSERT pattern with sub-batching
- Added import_candidates_jsonl to candidate_import_service for person-entity model (no election_id)
- Registered five new CLI commands: election-events, elections, candidacies, candidates-jsonl, election-data
- Pipeline command runs imports in FK dependency order (events -> elections -> candidates -> candidacies) and stops on failure
- Implemented migrate-format command with Body/Seat inference, candidate table column reduction, and idempotency
- Implemented backfill-uuids command matching files to DB records by natural key
- All import services support --dry-run mode
- Integration tests verify import, dry-run, and validation error handling

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing import tests** - `f67f9b5` (test)
2. **Task 1 (GREEN): Implement import services and CLI** - `4d4c3e6` (feat)
3. **Task 2: File migration, UUID backfill, and E2E tests** - `4303dc2` (feat)

_TDD task had RED/GREEN commits. No refactor phase needed._

## Files Created/Modified
- `src/voter_api/services/jsonl_reader.py` - Shared JSONL reader with Pydantic per-line validation
- `src/voter_api/services/election_event_import_service.py` - ElectionEvent UPSERT import on UUID PK
- `src/voter_api/services/election_import_service.py` - Election UPSERT import on UUID PK
- `src/voter_api/services/candidacy_import_service.py` - Candidacy UPSERT import with COALESCE for nullable fields
- `src/voter_api/services/candidate_import_service.py` - Added import_candidates_jsonl for person-entity model
- `src/voter_api/cli/import_cmd.py` - Five new CLI commands (election-events, elections, candidacies, candidates-jsonl, election-data)
- `src/voter_api/cli/convert_cmd.py` - Added migrate-format and backfill-uuids commands
- `tests/integration/test_election_event_import.py` - 7 integration tests for import services
- `tests/e2e/test_smoke.py` - 2 new tests in TestImportPipeline class (166 total E2E tests)

## Decisions Made
- Created separate `candidates-jsonl` command for the new person-entity model rather than modifying the existing `candidates` command. The existing command handles legacy preprocessed JSONL with election resolution; the new one handles CandidateJSONL person entities without election_id.
- Pipeline command uses separate async sessions per file type for isolation. If elections import fails, election-events changes are already committed.
- UUID backfill queries DB directly via SQLAlchemy select rather than through import services, since it only needs read access for matching.
- File migration detects idempotency by checking for `| Format Version |` row presence -- simpler and more reliable than checking all possible migration markers.
- Candidacy import uses COALESCE for nullable fields (party, contest_name, qualified_date, etc.) to preserve richer existing data on re-import, matching the pattern established in Plan 02-01.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in unrelated test files (test_seed_cmd, test_attachments_api, test_candidate_api, test_geocode_endpoint) due to missing env vars or configuration. These are not caused by this plan's changes and were excluded from verification runs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (Converter and Import Pipeline) is now complete
- Full pipeline works: markdown files -> converter -> JSONL -> import services -> database
- File migration and UUID backfill commands ready for processing existing ~200 markdown files
- All 159 county reference files have governing bodies tables for Body/Seat resolution
- Phase 3 (Skills) can proceed with all data pipeline infrastructure in place

## Self-Check: PASSED

- All 6 created files verified on disk
- All 3 task commits verified in git log

---
*Phase: 02-converter-and-import-pipeline*
*Completed: 2026-03-15*
