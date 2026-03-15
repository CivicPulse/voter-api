---
phase: 02-converter-and-import-pipeline
plan: 01
subsystem: database, api
tags: [sqlalchemy, alembic, pydantic, candidacy, junction-table, data-migration]

# Dependency graph
requires:
  - phase: 01-data-contracts
    provides: JSONL schemas defining target model shape (CandidacyJSONL, CandidateJSONL, ElectionEventJSONL, ElectionJSONL)
provides:
  - Candidacy ORM model (candidate-election junction table)
  - Updated Candidate model (nullable election_id, external_ids JSONB)
  - Enhanced ElectionEvent model (calendar/feed fields)
  - Election model with election_stage field
  - Alembic migration with data migration SQL
  - CandidacyResponse/CandidacySummaryResponse API schemas
  - Candidate import service creates candidacy records alongside candidates
  - E2E test fixtures and assertions for candidacy data
affects: [02-converter-and-import-pipeline, 03-skills]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Junction table pattern for many-to-many candidate-election relationships"
    - "Additive-first migration: add new tables/columns before removing old ones"
    - "Data migration in Alembic: copy candidate contest data to candidacies table"
    - "Safe mock handling in service layer (isinstance checks for dict/list from getattr)"

key-files:
  created:
    - src/voter_api/models/candidacy.py
    - src/voter_api/schemas/candidacy.py
    - alembic/versions/e3a1b5c8d902_add_candidacy_table_and_refactor_models.py
  modified:
    - src/voter_api/models/candidate.py
    - src/voter_api/models/election.py
    - src/voter_api/models/election_event.py
    - src/voter_api/models/__init__.py
    - src/voter_api/schemas/candidate.py
    - src/voter_api/schemas/election.py
    - src/voter_api/services/candidate_service.py
    - src/voter_api/services/candidate_import_service.py
    - src/voter_api/api/v1/candidates.py
    - tests/e2e/conftest.py
    - tests/e2e/test_smoke.py

key-decisions:
  - "Used TYPE_CHECKING for Candidacy model imports to avoid circular import with Election model"
  - "Safe external_ids extraction with isinstance(dict) check to handle mock objects in unit tests"
  - "Candidacy upsert uses COALESCE for nullable fields to preserve richer existing data on re-import"
  - "Additive-first: kept Candidate.election_id and all existing fields, only made it nullable"

patterns-established:
  - "Junction table with CASCADE FKs and unique constraint on (candidate_id, election_id)"
  - "Data migration SQL in Alembic upgrade() after schema changes"
  - "Candidacy records created alongside candidate records in import service"

requirements-completed: [IMP-01, IMP-02]

# Metrics
duration: 13min
completed: 2026-03-15
---

# Phase 2 Plan 01: DB Migrations and Model Refactoring Summary

**Candidacy junction table, ElectionEvent calendar/feed fields, and additive-first Alembic migration with data migration SQL**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-15T01:35:11Z
- **Completed:** 2026-03-15T01:49:00Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments
- Created Candidacy ORM model as candidate-election junction table with all contest-specific fields
- Enhanced ElectionEvent model with calendar dates (registration_deadline, early_voting, qualifying) and feed fields (data_source_url, refresh_interval)
- Added Alembic migration with SQL data migration that copies existing candidate contest data to candidacies table
- Updated candidate import service to create candidacy records alongside candidates using UPSERT pattern
- Updated API schemas and E2E tests to reflect the new model structure

## Task Commits

Each task was committed atomically:

1. **Task 1: Alembic migration and ORM model updates** - `4b61627` (feat)
2. **Task 2: API schemas, candidate import service, and E2E test fixes** - `2cc36ff` (feat)

## Files Created/Modified
- `src/voter_api/models/candidacy.py` - Candidacy ORM model (candidate-election junction)
- `src/voter_api/models/candidate.py` - Made election_id nullable, added external_ids JSONB, candidacies relationship
- `src/voter_api/models/election.py` - Added election_stage field and candidacies relationship
- `src/voter_api/models/election_event.py` - Added calendar fields, feed fields, election_stage
- `src/voter_api/models/__init__.py` - Registered Candidacy model
- `alembic/versions/e3a1b5c8d902_add_candidacy_table_and_refactor_models.py` - Migration with data migration SQL
- `src/voter_api/schemas/candidacy.py` - CandidacyResponse and CandidacySummaryResponse schemas
- `src/voter_api/schemas/candidate.py` - Added candidacies and external_ids to response schemas
- `src/voter_api/schemas/election.py` - Added election_stage to ElectionSummary
- `src/voter_api/services/candidate_service.py` - Eager-load candidacies, include in responses
- `src/voter_api/services/candidate_import_service.py` - Upsert candidacy records during import
- `src/voter_api/api/v1/candidates.py` - Serialize candidacies in list responses
- `tests/e2e/conftest.py` - Seed candidacy data with CANDIDACY_ID
- `tests/e2e/test_smoke.py` - Assertions for candidacies and election_stage

## Decisions Made
- Used `TYPE_CHECKING` for Candidacy model imports to prevent circular import between candidacy.py and election.py (both reference each other via relationships)
- Added `isinstance` checks for `external_ids` and `candidacies` in `build_candidate_detail_response` to safely handle mock objects in unit tests
- Candidacy UPSERT in import service uses `COALESCE` for nullable fields (party, contest_name, etc.) to preserve richer existing data when a sparse re-import comes in
- Followed additive-first principle: existing Candidate fields (election_id, party, contest_name, etc.) are kept intact alongside the new candidacies table

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed circular import between candidacy.py and election.py**
- **Found during:** Task 1 (ORM model updates)
- **Issue:** Direct imports between candidacy.py and election.py caused ImportError
- **Fix:** Used TYPE_CHECKING guard for forward references in candidacy.py
- **Files modified:** src/voter_api/models/candidacy.py
- **Verification:** `from voter_api.models import Candidacy` succeeds
- **Committed in:** 4b61627 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed mock object validation in build_candidate_detail_response**
- **Found during:** Task 2 (service updates)
- **Issue:** `getattr(candidate, "external_ids", None)` returns MagicMock when candidate is mocked, causing Pydantic validation error
- **Fix:** Added isinstance checks for dict (external_ids) and list (candidacies) before passing to Pydantic
- **Files modified:** src/voter_api/services/candidate_service.py
- **Verification:** All 30 candidate service unit tests pass
- **Committed in:** 2cc36ff (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes were necessary for correct operation. No scope creep.

## Issues Encountered
- Pre-existing test failure in `tests/unit/lib/test_converter/test_directory.py` (references `voter_api.lib.converter.report` which doesn't exist yet -- Plan 02-02 deliverable). Excluded from test runs with `--ignore`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Database schema is ready for the converter library (Plan 02-02) and import pipeline (Plan 02-03)
- Candidacy junction table enables the converter to map candidate-election relationships
- ElectionEvent calendar/feed fields enable the import pipeline to populate event-level data
- Existing candidate import service works with the updated model structure

---
*Phase: 02-converter-and-import-pipeline*
*Completed: 2026-03-15*
